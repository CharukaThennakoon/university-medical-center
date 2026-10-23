"""
modules/doctor/services.py - Doctor module logic.

  get_today_queue()        today's tokens with patient info
  list_medicines()         inventory with GREEN / RED stock indicator
  start_consultation()     Pending -> In-Consultation
  parse_prescription_form() validates diagnosis + medicine lines
  create_prescription()    ONE transaction: save prescription, deduct stock,
                           send to pharmacy queue, complete the token
"""
from datetime import date

from mysql.connector import Error

from database.db_connection import db_cursor

MAX_QTY = 999


class PrescriptionError(Exception):
    """A prescription could not be saved; the message is shown to the doctor."""


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
def get_today_queue(cur):
    cur.execute(
        "SELECT t.token_id, t.token_number, t.status, t.issued_at, "
        "       p.patient_id, p.ar_number, p.special_conditions, "
        "       CONCAT(p.first_name, ' ', p.last_name) AS patient_name "
        "FROM Daily_Tokens t "
        "JOIN Students_Patients p ON p.patient_id = t.patient_id "
        "WHERE t.token_date = CURDATE() ORDER BY t.token_number")
    return cur.fetchall()


def get_doctors(cur):
    cur.execute("SELECT doctor_id, doctor_name, specialization, is_available "
                "FROM Doctors ORDER BY doctor_id")
    return cur.fetchall()


def get_token_detail(cur, token_id):
    cur.execute(
        "SELECT t.token_id, t.token_number, t.token_date, t.status, t.issued_at, "
        "       (t.token_date = CURDATE()) AS is_today, "
        "       p.patient_id, p.ar_number, p.nic_number, p.first_name, p.last_name, "
        "       p.address, p.height, p.weight, p.special_conditions "
        "FROM Daily_Tokens t "
        "JOIN Students_Patients p ON p.patient_id = t.patient_id "
        "WHERE t.token_id = %s", (token_id,))
    return cur.fetchone()


def list_medicines(cur):
    """
    Uses the v_medicine_stock view:
        stock_indicator = 'GREEN' when stock_quantity > 0, 'RED' when it is 0.
    Expired medicines are flagged and cannot be selected.
    """
    cur.execute(
        "SELECT medicine_id, medicine_name, category, stock_quantity, "
        "       expiry_date, stock_indicator "
        "FROM v_medicine_stock ORDER BY medicine_name")
    medicines = cur.fetchall()
    today = date.today()
    for m in medicines:
        m["expired"] = bool(m["expiry_date"] and m["expiry_date"] < today)
        m["selectable"] = m["stock_quantity"] > 0 and not m["expired"]
    return medicines


# ---------------------------------------------------------------------------
# Small writes
# ---------------------------------------------------------------------------
def start_consultation(token_id):
    """Pending -> In-Consultation (today's tokens only). True if it changed."""
    with db_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE Daily_Tokens SET status = 'In-Consultation' "
            "WHERE token_id = %s AND token_date = CURDATE() AND status = 'Pending'",
            (token_id,))
        started = cur.rowcount == 1
    return started


def set_availability(doctor_id, available):
    with db_cursor(commit=True) as cur:
        cur.execute("UPDATE Doctors SET is_available = %s WHERE doctor_id = %s",
                    (1 if available else 0, doctor_id))


# ---------------------------------------------------------------------------
# Prescription form validation
# ---------------------------------------------------------------------------
def parse_prescription_form(form):
    """
    Returns (diagnosis, items, errors, raw_lines).
      items     : cleaned [{'medicine_id', 'dosage', 'quantity'}]
      raw_lines : the lines as typed, used to refill the form after an error
    The medicine lines are optional (advice-only consultations are allowed).
    """
    diagnosis = (form.get("diagnosis") or "").strip()
    ids = form.getlist("medicine_id")
    dosages = form.getlist("dosage")
    quantities = form.getlist("quantity")
    errors, items, raw = [], [], []

    if not diagnosis:
        errors.append("Diagnosis is required.")
    elif len(diagnosis) > 2000:
        errors.append("Diagnosis must be 2000 characters or fewer.")

    if not (len(ids) == len(dosages) == len(quantities)):
        errors.append("The medicine lines were incomplete. Please add them again.")
        return diagnosis, items, errors, raw

    seen = set()
    for n, (mid, dosage, qty) in enumerate(zip(ids, dosages, quantities), start=1):
        mid, dosage, qty = mid.strip(), dosage.strip(), qty.strip()
        if not (mid or dosage or qty):
            continue
        raw.append({"medicine_id": mid, "dosage": dosage, "quantity": qty})

        if not (mid.isascii() and mid.isdigit() and len(mid) <= 9):
            errors.append(f"Line {n}: invalid medicine.")
        elif not (qty.isascii() and qty.isdigit() and len(qty) <= 4
                  and 1 <= int(qty) <= MAX_QTY):
            errors.append(f"Line {n}: quantity must be a whole number from 1 to {MAX_QTY}.")
        elif not dosage:
            errors.append(f"Line {n}: dosage instructions are required.")
        elif len(dosage) > 100:
            errors.append(f"Line {n}: dosage must be 100 characters or fewer.")
        elif int(mid) in seen:
            errors.append(f"Line {n}: the same medicine was added twice.")
        else:
            seen.add(int(mid))
            items.append({"medicine_id": int(mid), "dosage": dosage,
                          "quantity": int(qty)})
    return diagnosis, items, errors, raw


# ---------------------------------------------------------------------------
# The prescribing transaction
# ---------------------------------------------------------------------------
def create_prescription(token_id, doctor_id, diagnosis, items):
    """
    Everything happens in ONE database transaction - all or nothing:
      1. lock the token row and check it is today's, In-Consultation token
      2. insert the prescription (status Pending = shows in the pharmacy queue;
         no medicines -> status Dispensed, so the pharmacy never sees it)
      3. for each medicine: deduct stock with a guarded UPDATE
             SET stock = stock - qty WHERE stock >= qty
         so stock can never go negative, even if two doctors prescribe the
         same medicine at the same moment
      4. save the prescription items
      5. mark the token Completed
    Any problem raises PrescriptionError and rolls EVERYTHING back
    (including stock already deducted for earlier lines).
    Returns {'prescription_id', 'token_number', 'sent_to_pharmacy'}.
    """
    # Always touch medicines in the same order -> two doctors cannot deadlock
    items = sorted(items, key=lambda i: i["medicine_id"])
    try:
        with db_cursor(commit=True) as cur:
            cur.execute(
                "SELECT token_id, token_number, patient_id, status "
                "FROM Daily_Tokens WHERE token_id = %s AND token_date = CURDATE() "
                "FOR UPDATE", (token_id,))
            token = cur.fetchone()
            if not token:
                raise PrescriptionError("This token was not found among today's tokens.")
            if token["status"] != "In-Consultation":
                raise PrescriptionError(
                    f"This consultation is not open (token status: {token['status']}).")

            status = "Pending" if items else "Dispensed"
            cur.execute(
                "INSERT INTO Prescriptions "
                "(token_id, patient_id, doctor_id, diagnosis, status) "
                "VALUES (%s, %s, %s, %s, %s)",
                (token_id, token["patient_id"], doctor_id, diagnosis, status))
            prescription_id = cur.lastrowid

            for item in items:
                cur.execute(
                    "UPDATE Medicines_Inventory "
                    "SET stock_quantity = stock_quantity - %s "
                    "WHERE medicine_id = %s AND stock_quantity >= %s "
                    "  AND (expiry_date IS NULL OR expiry_date >= CURDATE())",
                    (item["quantity"], item["medicine_id"], item["quantity"]))
                if cur.rowcount != 1:
                    cur.execute(
                        "SELECT medicine_name, stock_quantity, "
                        "       (expiry_date IS NOT NULL AND expiry_date < CURDATE()) AS expired "
                        "FROM Medicines_Inventory WHERE medicine_id = %s",
                        (item["medicine_id"],))
                    med = cur.fetchone()
                    if not med:
                        raise PrescriptionError("A selected medicine no longer exists.")
                    if med["expired"]:
                        raise PrescriptionError(
                            f"{med['medicine_name']} has expired and cannot be prescribed.")
                    raise PrescriptionError(
                        f"Not enough stock for {med['medicine_name']}: "
                        f"{med['stock_quantity']} left, {item['quantity']} requested.")

                cur.execute(
                    "INSERT INTO Prescription_Items "
                    "(prescription_id, medicine_id, dosage, quantity_given) "
                    "VALUES (%s, %s, %s, %s)",
                    (prescription_id, item["medicine_id"], item["dosage"],
                     item["quantity"]))

            cur.execute("UPDATE Daily_Tokens SET status = 'Completed' "
                        "WHERE token_id = %s", (token_id,))
        return {"prescription_id": prescription_id,
                "token_number": token["token_number"],
                "sent_to_pharmacy": bool(items)}
    except Error as e:
        if e.errno == 1062:  # uq_prescription_token: already prescribed
            raise PrescriptionError(
                "A prescription has already been written for this token.")
        raise
