"""
modules/patients/services.py - Logic shared by the Student and Counter modules.

  validate_patient_form()  -> checks the registration form
  register_patient()       -> saves patient (+ optional login account) atomically
  issue_token()            -> issues today's token through sp_issue_token
  find_patient_by_ar() / get_open_token_today() -> small lookup helpers
"""
import re
from decimal import Decimal, InvalidOperation

from mysql.connector import Error
from werkzeug.security import generate_password_hash

from database.db_connection import db_cursor

# Characters never expected in a person's name (digits, brackets, symbols ...)
BAD_NAME_CHARS = re.compile(r"[\d<>{}\[\]()\\/@#$%^&*=+|~`;:\"?!_]")
# Sri Lankan NIC: old format 9 digits + V/X, new format 12 digits
NIC_RE = re.compile(r"^(?:\d{9}[VX]|\d{12})$")
# AR number, e.g. AR1001 (letters, digits, / and - allowed)
AR_RE = re.compile(r"^[A-Z0-9/\-]{3,20}$")

MIN_PASSWORD = 8
MAX_PASSWORD = 128


class TokenError(Exception):
    """A token could not be issued for a business reason (shown to the user)."""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_patient_form(form, password_required):
    """
    Returns (data, errors). `errors` maps field name -> message.
    password_required=True  : self-registration (a login account is created)
    password_required=False : counter registration (password is optional)
    """
    def g(key):
        return (form.get(key) or "").strip()

    data = {
        "first_name": g("first_name"),
        "last_name": g("last_name"),
        "nic_number": g("nic_number").upper(),
        "ar_number": g("ar_number").upper(),
        "address": g("address"),
        "height": g("height"),
        "weight": g("weight"),
        "special_conditions": g("special_conditions"),
        "password": form.get("password") or "",
        "confirm_password": form.get("confirm_password") or "",
    }
    errors = {}

    for key, label in (("first_name", "First name"), ("last_name", "Last name")):
        value = data[key]
        if not value:
            errors[key] = f"{label} is required."
        elif len(value) > 50:
            errors[key] = f"{label} must be 50 characters or fewer."
        elif BAD_NAME_CHARS.search(value):
            errors[key] = f"{label} contains invalid characters."

    if not data["nic_number"]:
        errors["nic_number"] = "NIC number is required."
    elif not NIC_RE.match(data["nic_number"]):
        errors["nic_number"] = "Enter a valid NIC (9 digits + V, or 12 digits)."

    if not data["ar_number"]:
        errors["ar_number"] = "AR number is required."
    elif not AR_RE.match(data["ar_number"]):
        errors["ar_number"] = "AR number may contain letters, digits, / and - (3-20 characters)."

    if not data["address"]:
        errors["address"] = "Address is required."
    elif len(data["address"]) > 255:
        errors["address"] = "Address must be 255 characters or fewer."

    for key, label, low, high in (("height", "Height (cm)", 50, 250),
                                  ("weight", "Weight (kg)", 10, 300)):
        raw = data[key]
        if not raw:
            data[key] = None  # optional
            continue
        try:
            number = Decimal(raw)
        except InvalidOperation:
            errors[key] = f"{label} must be a number."
            continue
        if not number.is_finite() or not (low <= number <= high):
            errors[key] = f"{label} must be between {low} and {high}."
        else:
            data[key] = number.quantize(Decimal("0.01"))

    if len(data["special_conditions"]) > 1000:
        errors["special_conditions"] = "Please keep this under 1000 characters."

    password = data["password"]
    if password_required or password:
        if len(password) < MIN_PASSWORD:
            errors["password"] = f"Password must be at least {MIN_PASSWORD} characters."
        elif len(password) > MAX_PASSWORD:
            errors["password"] = f"Password must be at most {MAX_PASSWORD} characters."
        elif password != data["confirm_password"]:
            errors["confirm_password"] = "Passwords do not match."

    return data, errors


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
def _check_duplicates(cur, data, create_account):
    errors = {}
    cur.execute(
        "SELECT ar_number, nic_number FROM Students_Patients "
        "WHERE ar_number = %s OR nic_number = %s",
        (data["ar_number"], data["nic_number"]))
    for row in cur.fetchall():
        if row["ar_number"].upper() == data["ar_number"]:
            errors["ar_number"] = "This AR number is already registered."
        if row["nic_number"].upper() == data["nic_number"]:
            errors["nic_number"] = "This NIC number is already registered."

    if create_account and "ar_number" not in errors:
        # the AR number becomes the username
        cur.execute("SELECT 1 AS found FROM Users_Roles "
                    "WHERE LOWER(username) = LOWER(%s)", (data["ar_number"],))
        if cur.fetchone():
            errors["ar_number"] = "A login account with this AR number already exists."
    return errors


def register_patient(data, create_account):
    """
    Saves the patient and (optionally) the Student login account in ONE
    transaction: both rows are saved, or neither.
    Returns (patient_id, errors). Unexpected DB failures raise mysql Error.
    """
    try:
        with db_cursor(commit=True) as cur:
            errors = _check_duplicates(cur, data, create_account)
            if errors:
                return None, errors

            cur.execute(
                "INSERT INTO Students_Patients "
                "(ar_number, nic_number, first_name, last_name, address, "
                " height, weight, special_conditions) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (data["ar_number"], data["nic_number"], data["first_name"],
                 data["last_name"], data["address"], data["height"],
                 data["weight"], data["special_conditions"] or None))
            patient_id = cur.lastrowid

            if create_account:
                cur.execute(
                    "INSERT INTO Users_Roles (username, password_hash, role, ref_id) "
                    "VALUES (%s, %s, 'Student', %s)",
                    (data["ar_number"],
                     generate_password_hash(data["password"], method="pbkdf2:sha256"),
                     patient_id))
            return patient_id, {}
    except Error as e:
        if e.errno == 1062:  # duplicate key (two people registering at once)
            return None, {"ar_number": "This AR number or NIC is already registered."}
        raise


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------
def find_patient_by_ar(cur, ar_number):
    cur.execute(
        "SELECT patient_id, ar_number, nic_number, first_name, last_name, "
        "       address, height, weight, special_conditions "
        "FROM Students_Patients WHERE ar_number = %s", (ar_number,))
    return cur.fetchone()


def get_open_token_today(cur, patient_id):
    cur.execute(
        "SELECT token_id, token_number, status FROM Daily_Tokens "
        "WHERE patient_id = %s AND token_date = CURDATE() "
        "  AND status IN ('Pending', 'In-Consultation') "
        "ORDER BY token_id DESC LIMIT 1", (patient_id,))
    return cur.fetchone()


# ---------------------------------------------------------------------------
# Daily token (numbers restart at 1 every day - see sp_issue_token in schema.sql)
# ---------------------------------------------------------------------------
def issue_token(patient_id):
    """
    Returns {'token_id', 'token_number', 'patient_name'} for the new token.
    Raises TokenError for business-rule failures (e.g. already has a token).
    """
    try:
        with db_cursor(commit=True) as cur:
            cur.callproc("sp_issue_token", (patient_id,))
            for _ in cur.stored_results():  # consume the procedure's own result set
                pass
            cur.execute(
                "SELECT t.token_id, t.token_number, "
                "       CONCAT(p.first_name, ' ', p.last_name) AS patient_name "
                "FROM Daily_Tokens t "
                "JOIN Students_Patients p ON p.patient_id = t.patient_id "
                "WHERE t.patient_id = %s AND t.token_date = CURDATE() "
                "ORDER BY t.token_id DESC LIMIT 1", (patient_id,))
            token = cur.fetchone()
        return token
    except Error as e:
        if e.errno == 1644:  # SIGNAL SQLSTATE '45000' raised by sp_issue_token
            raise TokenError(e.msg)
        raise
