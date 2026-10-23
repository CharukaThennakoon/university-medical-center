"""
modules/admin/services.py - Administrator logic.

  Dashboard      get_dashboard_stats()
  Users          list_users(), create_staff_user(), reset_password(), set_user_active()
  Doctors        list_doctors(), create_doctor(), update_doctor()
  Medicines      list_medicines(), create_medicine(), update_medicine(), adjust_stock()
  Patients       list_patients(), get_patient(), update_patient()   (identity fields only)
  Reports        visits_per_day(), top_medicines(), doctor_workload()
  Audit          list_audit()

Every change is written to Audit_Log in the SAME transaction as the change,
so a change can never exist without its log line.

Privacy rule: the Admin manages accounts, staff and stock. The Admin pages never
show diagnoses or prescriptions, and the Admin cannot edit a patient's medical
details (special conditions, height, weight).
"""
import re
from datetime import date

from mysql.connector import Error
from werkzeug.security import generate_password_hash

from database.db_connection import db_cursor
from modules.patients.services import (BAD_NAME_CHARS, MAX_PASSWORD,
                                       MIN_PASSWORD, validate_patient_form)

LOW_STOCK = 20            # stock at or below this (but above 0) = "low"
EXPIRY_WARN_DAYS = 60     # expiring within this many days = "expiring soon"
MAX_STOCK = 1_000_000

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,50}$")
STAFF_ROLES = ("Pharmacist", "CounterOfficer", "Admin")


class AdminError(Exception):
    """A business-rule failure; the message is shown to the admin."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _audit(cur, actor, action, detail=None):
    cur.execute(
        "INSERT INTO Audit_Log (user_id, username, action, detail) VALUES (%s, %s, %s, %s)",
        (actor["user_id"], actor["username"], action, (detail or "")[:500] or None))


def _hash(password):
    return generate_password_hash(password, method="pbkdf2:sha256")


def check_password(password, confirm):
    """Returns an error message, or None when the password is acceptable."""
    if len(password) < MIN_PASSWORD:
        return f"Password must be at least {MIN_PASSWORD} characters."
    if len(password) > MAX_PASSWORD:
        return f"Password must be at most {MAX_PASSWORD} characters."
    if password != confirm:
        return "Passwords do not match."
    return None


def _like(text):
    """Escape LIKE wildcards so the admin's search text is matched literally."""
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _username_taken(cur, username):
    cur.execute("SELECT 1 AS x FROM Users_Roles WHERE LOWER(username) = LOWER(%s)", (username,))
    return cur.fetchone() is not None


def _g(form, key):
    return (form.get(key) or "").strip()


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
def get_dashboard_stats(cur):
    s = {}
    cur.execute("SELECT COUNT(*) AS n FROM Students_Patients")
    s["patients"] = cur.fetchone()["n"]

    tokens = {"Pending": 0, "In-Consultation": 0, "Completed": 0}
    cur.execute("SELECT status, COUNT(*) AS n FROM Daily_Tokens "
                "WHERE token_date = CURDATE() GROUP BY status")
    for r in cur.fetchall():
        tokens[r["status"]] = r["n"]
    s["tokens"] = tokens

    cur.execute("SELECT COUNT(*) AS n FROM Prescriptions rx "
                "WHERE rx.status = 'Pending'")
    s["rx_pending"] = cur.fetchone()["n"]

    cur.execute("SELECT role, COUNT(*) AS n, COALESCE(SUM(is_active = 0), 0) AS inactive "
                "FROM Users_Roles GROUP BY role")
    s["users"] = {r["role"]: r for r in cur.fetchall()}

    cur.execute("SELECT COUNT(*) AS total, "
                "       COALESCE(SUM(is_available = 1), 0) AS available FROM Doctors")
    s["doctors"] = cur.fetchone()

    cur.execute(
        "SELECT COALESCE(SUM(stock_quantity = 0), 0) AS out_of_stock, "
        "       COALESCE(SUM(stock_quantity BETWEEN 1 AND %s), 0) AS low, "
        "       COALESCE(SUM(expiry_date IS NOT NULL AND expiry_date < CURDATE()), 0) AS expired, "
        "       COALESCE(SUM(expiry_date IS NOT NULL AND expiry_date >= CURDATE() "
        "                    AND expiry_date <= DATE_ADD(CURDATE(), INTERVAL %s DAY)), 0) AS expiring "
        "FROM Medicines_Inventory", (LOW_STOCK, EXPIRY_WARN_DAYS))
    s["stock"] = cur.fetchone()

    cur.execute(
        "SELECT medicine_id, medicine_name, stock_quantity, expiry_date "
        "FROM Medicines_Inventory "
        "WHERE stock_quantity <= %s OR (expiry_date IS NOT NULL "
        "      AND expiry_date <= DATE_ADD(CURDATE(), INTERVAL %s DAY)) "
        "ORDER BY stock_quantity, expiry_date LIMIT 10", (LOW_STOCK, EXPIRY_WARN_DAYS))
    s["attention"] = _flag_medicines(cur.fetchall())
    return s


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
def list_users(cur, q="", limit=200):
    sql = ("SELECT u.user_id, u.username, u.role, u.is_active, "
           "  CASE u.role "
           "    WHEN 'Student' THEN (SELECT CONCAT(p.first_name, ' ', p.last_name) "
           "                          FROM Students_Patients p WHERE p.patient_id = u.ref_id) "
           "    WHEN 'Doctor'  THEN (SELECT d.doctor_name FROM Doctors d "
           "                          WHERE d.doctor_id = u.ref_id) "
           "    ELSE NULL END AS display_name "
           "FROM Users_Roles u ")
    params = []
    if q:
        sql += "WHERE u.username LIKE %s OR u.role LIKE %s "
        params += [_like(q), _like(q)]
    sql += ("ORDER BY FIELD(u.role, 'Admin', 'Doctor', 'Pharmacist', 'CounterOfficer', 'Student'), "
            "u.username LIMIT %s")
    params.append(int(limit))
    cur.execute(sql, params)
    return cur.fetchall()


def create_staff_user(actor, form):
    """Pharmacist / CounterOfficer / Admin login. Doctors are created on the Doctors page."""
    username, role = _g(form, "username"), _g(form, "role")
    password, confirm = form.get("password") or "", form.get("confirm_password") or ""
    errors = []
    if not USERNAME_RE.match(username):
        errors.append("Username must be 3-50 characters: letters, digits, . _ -")
    if role not in STAFF_ROLES:
        errors.append("Choose a valid role.")
    pw_error = check_password(password, confirm)
    if pw_error:
        errors.append(pw_error)
    if errors:
        return errors

    try:
        with db_cursor(commit=True) as cur:
            if _username_taken(cur, username):
                return ["That username is already in use."]
            cur.execute("INSERT INTO Users_Roles (username, password_hash, role, ref_id) "
                        "VALUES (%s, %s, %s, NULL)", (username, _hash(password), role))
            _audit(cur, actor, "USER_CREATE", f"{role} account '{username}'")
    except Error as e:
        if e.errno == 1062:
            return ["That username is already in use."]
        raise
    return []


def reset_password(actor, user_id, form):
    password, confirm = form.get("password") or "", form.get("confirm_password") or ""
    pw_error = check_password(password, confirm)
    if pw_error:
        raise AdminError(pw_error)
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT username FROM Users_Roles WHERE user_id = %s", (user_id,))
        user = cur.fetchone()
        if not user:
            raise AdminError("User not found.")
        cur.execute("UPDATE Users_Roles SET password_hash = %s WHERE user_id = %s",
                    (_hash(password), user_id))
        _audit(cur, actor, "PASSWORD_RESET", f"account '{user['username']}'")
    return user["username"]


def set_user_active(actor, user_id, active):
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT user_id, username, role FROM Users_Roles "
                    "WHERE user_id = %s FOR UPDATE", (user_id,))
        user = cur.fetchone()
        if not user:
            raise AdminError("User not found.")
        if not active:
            if user["user_id"] == actor["user_id"]:
                raise AdminError("You cannot deactivate your own account.")
            if user["role"] == "Admin":
                cur.execute("SELECT COUNT(*) AS n FROM Users_Roles "
                            "WHERE role = 'Admin' AND is_active = 1 AND user_id <> %s",
                            (user_id,))
                if cur.fetchone()["n"] == 0:
                    raise AdminError("This is the last active Admin and cannot be deactivated.")
        cur.execute("UPDATE Users_Roles SET is_active = %s WHERE user_id = %s",
                    (1 if active else 0, user_id))
        _audit(cur, actor, "USER_ACTIVATE" if active else "USER_DEACTIVATE",
               f"account '{user['username']}'")
    return user["username"]


# ---------------------------------------------------------------------------
# Doctors
# ---------------------------------------------------------------------------
def list_doctors(cur):
    cur.execute(
        "SELECT d.doctor_id, d.doctor_name, d.specialization, d.is_available, "
        "       u.username, u.is_active "
        "FROM Doctors d "
        "LEFT JOIN Users_Roles u ON u.role = 'Doctor' AND u.ref_id = d.doctor_id "
        "ORDER BY d.doctor_id")
    return cur.fetchall()


def _validate_doctor(form):
    name, spec = _g(form, "doctor_name"), _g(form, "specialization") or "General Practitioner"
    errors = []
    if not name:
        errors.append("Doctor name is required.")
    elif len(name) > 100:
        errors.append("Doctor name must be 100 characters or fewer.")
    elif BAD_NAME_CHARS.search(name):
        errors.append("Doctor name contains invalid characters.")
    if len(spec) > 100:
        errors.append("Specialization must be 100 characters or fewer.")
    return name, spec, errors


def create_doctor(actor, form):
    """Doctor profile + login account, saved together (both or neither)."""
    name, spec, errors = _validate_doctor(form)
    username = _g(form, "username")
    password, confirm = form.get("password") or "", form.get("confirm_password") or ""
    if not USERNAME_RE.match(username):
        errors.append("Username must be 3-50 characters: letters, digits, . _ -")
    pw_error = check_password(password, confirm)
    if pw_error:
        errors.append(pw_error)
    if errors:
        return errors

    try:
        with db_cursor(commit=True) as cur:
            if _username_taken(cur, username):
                return ["That username is already in use."]
            cur.execute("INSERT INTO Doctors (doctor_name, specialization, is_available) "
                        "VALUES (%s, %s, 1)", (name, spec))
            doctor_id = cur.lastrowid
            cur.execute("INSERT INTO Users_Roles (username, password_hash, role, ref_id) "
                        "VALUES (%s, %s, 'Doctor', %s)", (username, _hash(password), doctor_id))
            _audit(cur, actor, "DOCTOR_CREATE", f"{name} (login '{username}')")
    except Error as e:
        if e.errno == 1062:
            return ["That username is already in use."]
        raise
    return []


def update_doctor(actor, doctor_id, form):
    name, spec, errors = _validate_doctor(form)
    if errors:
        return errors
    available = 1 if form.get("is_available") == "1" else 0
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT doctor_id FROM Doctors WHERE doctor_id = %s FOR UPDATE", (doctor_id,))
        if not cur.fetchone():
            raise AdminError("Doctor not found.")
        cur.execute("UPDATE Doctors SET doctor_name = %s, specialization = %s, is_available = %s "
                    "WHERE doctor_id = %s", (name, spec, available, doctor_id))
        _audit(cur, actor, "DOCTOR_UPDATE",
               f"#{doctor_id} {name}, {spec}, {'available' if available else 'not available'}")
    return []


# ---------------------------------------------------------------------------
# Medicines
# ---------------------------------------------------------------------------
def _flag_medicines(rows):
    today = date.today()
    for m in rows:
        exp = m["expiry_date"]
        m["expired"] = bool(exp and exp < today)
        m["expiring"] = bool(exp and not m["expired"] and (exp - today).days <= EXPIRY_WARN_DAYS)
        m["out"] = m["stock_quantity"] == 0
        m["low"] = 0 < m["stock_quantity"] <= LOW_STOCK
    return rows


def list_medicines(cur, q="", show="all"):
    sql = ("SELECT medicine_id, medicine_name, category, stock_quantity, expiry_date "
           "FROM Medicines_Inventory ")
    params = []
    if q:
        sql += "WHERE medicine_name LIKE %s OR category LIKE %s "
        params += [_like(q), _like(q)]
    sql += "ORDER BY medicine_name"
    cur.execute(sql, params)
    rows = _flag_medicines(cur.fetchall())
    if show == "attention":
        rows = [m for m in rows if m["out"] or m["low"] or m["expired"] or m["expiring"]]
    return rows


def _parse_medicine(form, with_stock):
    name, category = _g(form, "medicine_name"), _g(form, "category")
    errors = []
    if not name:
        errors.append("Medicine name is required.")
    elif len(name) > 100:
        errors.append("Medicine name must be 100 characters or fewer.")
    if not category:
        errors.append("Category is required.")
    elif len(category) > 60:
        errors.append("Category must be 60 characters or fewer.")

    expiry = None
    raw = _g(form, "expiry_date")
    if raw:
        try:
            expiry = date.fromisoformat(raw)
        except ValueError:
            errors.append("Expiry date is not a valid date.")

    stock = 0
    if with_stock:
        raw = _g(form, "stock_quantity") or "0"
        if raw.isascii() and raw.isdigit() and len(raw) <= 7 and int(raw) <= MAX_STOCK:
            stock = int(raw)
        else:
            errors.append(f"Stock must be a whole number from 0 to {MAX_STOCK}.")
    return {"medicine_name": name, "category": category,
            "expiry_date": expiry, "stock_quantity": stock}, errors


def create_medicine(actor, form):
    data, errors = _parse_medicine(form, with_stock=True)
    if errors:
        return errors
    try:
        with db_cursor(commit=True) as cur:
            cur.execute("INSERT INTO Medicines_Inventory "
                        "(medicine_name, category, stock_quantity, expiry_date) "
                        "VALUES (%s, %s, %s, %s)",
                        (data["medicine_name"], data["category"],
                         data["stock_quantity"], data["expiry_date"]))
            _audit(cur, actor, "MEDICINE_CREATE",
                   f"{data['medicine_name']} (stock {data['stock_quantity']})")
    except Error as e:
        if e.errno == 1062:
            return ["A medicine with this name already exists."]
        raise
    return []


def update_medicine(actor, medicine_id, form):
    """Name / category / expiry only. Stock is changed through adjust_stock()."""
    data, errors = _parse_medicine(form, with_stock=False)
    if errors:
        return errors
    try:
        with db_cursor(commit=True) as cur:
            cur.execute("SELECT medicine_id FROM Medicines_Inventory "
                        "WHERE medicine_id = %s FOR UPDATE", (medicine_id,))
            if not cur.fetchone():
                raise AdminError("Medicine not found.")
            cur.execute("UPDATE Medicines_Inventory SET medicine_name = %s, category = %s, "
                        "expiry_date = %s WHERE medicine_id = %s",
                        (data["medicine_name"], data["category"],
                         data["expiry_date"], medicine_id))
            _audit(cur, actor, "MEDICINE_UPDATE",
                   f"#{medicine_id} {data['medicine_name']}, {data['category']}, "
                   f"expiry {data['expiry_date'] or 'none'}")
    except Error as e:
        if e.errno == 1062:
            return ["Another medicine already has this name."]
        raise
    return []


def adjust_stock(actor, medicine_id, mode, raw_qty):
    """
    mode 'add' : restock - adds raw_qty to the current stock (safe while doctors
                 are prescribing, because the row is locked).
    mode 'set' : stock-take correction - sets the exact count.
    Returns (medicine_name, old_stock, new_stock).
    """
    raw_qty = (raw_qty or "").strip()
    if not (raw_qty.isascii() and raw_qty.isdigit() and len(raw_qty) <= 7):
        raise AdminError("Enter a whole number for the quantity.")
    qty = int(raw_qty)
    if mode not in ("add", "set"):
        raise AdminError("Unknown stock action.")
    if mode == "add" and qty < 1:
        raise AdminError("The quantity to add must be at least 1.")

    with db_cursor(commit=True) as cur:
        cur.execute("SELECT medicine_name, stock_quantity FROM Medicines_Inventory "
                    "WHERE medicine_id = %s FOR UPDATE", (medicine_id,))
        med = cur.fetchone()
        if not med:
            raise AdminError("Medicine not found.")
        old = med["stock_quantity"]
        new = old + qty if mode == "add" else qty
        if new > MAX_STOCK:
            raise AdminError(f"Stock cannot exceed {MAX_STOCK}.")
        cur.execute("UPDATE Medicines_Inventory SET stock_quantity = %s WHERE medicine_id = %s",
                    (new, medicine_id))
        _audit(cur, actor, "STOCK_ADD" if mode == "add" else "STOCK_SET",
               f"{med['medicine_name']}: {old} -> {new}")
    return med["medicine_name"], old, new


# ---------------------------------------------------------------------------
# Patients (identity fields only)
# ---------------------------------------------------------------------------
def list_patients(cur, q="", limit=100):
    sql = ("SELECT patient_id, ar_number, nic_number, first_name, last_name, address "
           "FROM Students_Patients ")
    params = []
    if q:
        sql += ("WHERE ar_number LIKE %s OR nic_number LIKE %s OR first_name LIKE %s "
                "OR last_name LIKE %s OR CONCAT(first_name, ' ', last_name) LIKE %s ")
        params += [_like(q)] * 5
    sql += "ORDER BY last_name, first_name LIMIT %s"
    params.append(int(limit))
    cur.execute(sql, params)
    return cur.fetchall()


def get_patient(cur, patient_id):
    cur.execute("SELECT patient_id, ar_number, nic_number, first_name, last_name, address "
                "FROM Students_Patients WHERE patient_id = %s", (patient_id,))
    return cur.fetchone()


def update_patient(actor, patient_id, form):
    """
    Fixes first name, last name and address (typos at registration).
    AR number is the student's username and NIC is a unique identity, so they
    are read-only here. Medical fields are not touched by the Admin.
    Returns (data, errors).
    """
    with db_cursor() as cur:
        patient = get_patient(cur, patient_id)
    if not patient:
        raise AdminError("Patient not found.")

    merged = {k: form.get(k) for k in ("first_name", "last_name", "address")}
    merged["ar_number"] = patient["ar_number"]
    merged["nic_number"] = patient["nic_number"]
    data, errors = validate_patient_form(merged, password_required=False)
    for key in ("ar_number", "nic_number", "height", "weight", "special_conditions",
                "password", "confirm_password"):
        errors.pop(key, None)
    if errors:
        return data, errors

    with db_cursor(commit=True) as cur:
        cur.execute("UPDATE Students_Patients SET first_name = %s, last_name = %s, address = %s "
                    "WHERE patient_id = %s",
                    (data["first_name"], data["last_name"], data["address"], patient_id))
        _audit(cur, actor, "PATIENT_UPDATE", f"{patient['ar_number']}: name/address corrected")
    return data, {}


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
def visits_per_day(cur, days=14):
    cur.execute(
        "SELECT token_date, COUNT(*) AS total, "
        "       SUM(status = 'Completed') AS completed "
        "FROM Daily_Tokens "
        "WHERE token_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY) "
        "GROUP BY token_date ORDER BY token_date DESC", (int(days),))
    return cur.fetchall()


def top_medicines(cur, days=30, limit=10):
    cur.execute(
        "SELECT m.medicine_name, SUM(i.quantity_given) AS units, "
        "       COUNT(DISTINCT i.prescription_id) AS prescriptions "
        "FROM Prescription_Items i "
        "JOIN Prescriptions rx ON rx.prescription_id = i.prescription_id "
        "JOIN Medicines_Inventory m ON m.medicine_id = i.medicine_id "
        "WHERE rx.prescribed_at >= DATE_SUB(CURDATE(), INTERVAL %s DAY) "
        "GROUP BY m.medicine_id, m.medicine_name "
        "ORDER BY units DESC LIMIT %s", (int(days), int(limit)))
    return cur.fetchall()


def doctor_workload(cur, days=30):
    cur.execute(
        "SELECT d.doctor_name, COUNT(rx.prescription_id) AS consultations "
        "FROM Doctors d "
        "LEFT JOIN Prescriptions rx ON rx.doctor_id = d.doctor_id "
        "     AND rx.prescribed_at >= DATE_SUB(CURDATE(), INTERVAL %s DAY) "
        "GROUP BY d.doctor_id, d.doctor_name ORDER BY consultations DESC", (int(days),))
    return cur.fetchall()


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
def list_audit(cur, limit=200):
    cur.execute("SELECT log_id, username, action, detail, created_at FROM Audit_Log "
                "ORDER BY log_id DESC LIMIT %s", (int(limit),))
    return cur.fetchall()
