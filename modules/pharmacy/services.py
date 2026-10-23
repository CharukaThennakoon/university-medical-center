"""
modules/pharmacy/services.py - Pharmacy module logic.

  get_pending_queue()        prescriptions waiting to be packed (by token number)
  get_prescription_detail()  one prescription with its medicine lines + stock
  get_stock()                inventory with GREEN / RED indicator
  dispense_prescription()    Pending -> Dispensed (after every line is packed)

IMPORTANT: stock was already deducted when the doctor prescribed (Phase 5),
so dispensing only changes the prescription status. Stock is never touched twice.
"""
from datetime import date

from database.db_connection import db_cursor


class DispenseError(Exception):
    """The prescription could not be dispensed; message is shown to the pharmacist."""


# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------
def get_pending_queue(cur):
    """
    All Pending prescriptions, oldest day first, then by token number.
    Older days are kept visible (flagged in the UI) so nothing gets lost.
    """
    cur.execute(
        "SELECT rx.prescription_id, rx.prescribed_at, t.token_number, t.token_date, "
        "       (t.token_date = CURDATE()) AS is_today, "
        "       p.ar_number, p.special_conditions, d.doctor_name, "
        "       CONCAT(p.first_name, ' ', p.last_name) AS patient_name, "
        "       (SELECT COUNT(*) FROM Prescription_Items i "
        "         WHERE i.prescription_id = rx.prescription_id) AS item_count "
        "FROM Prescriptions rx "
        "JOIN Daily_Tokens t     ON t.token_id   = rx.token_id "
        "JOIN Students_Patients p ON p.patient_id = rx.patient_id "
        "JOIN Doctors d          ON d.doctor_id  = rx.doctor_id "
        "WHERE rx.status = 'Pending' "
        "ORDER BY t.token_date, t.token_number")
    return cur.fetchall()


def get_dispensed_today(cur, limit=10):
    """Prescriptions written today that have been dispensed (advice-only visits excluded)."""
    cur.execute(
        "SELECT rx.prescription_id, t.token_number, rx.prescribed_at, "
        "       CONCAT(p.first_name, ' ', p.last_name) AS patient_name, p.ar_number "
        "FROM Prescriptions rx "
        "JOIN Daily_Tokens t     ON t.token_id   = rx.token_id "
        "JOIN Students_Patients p ON p.patient_id = rx.patient_id "
        "WHERE rx.status = 'Dispensed' AND DATE(rx.prescribed_at) = CURDATE() "
        "  AND EXISTS (SELECT 1 FROM Prescription_Items i "
        "               WHERE i.prescription_id = rx.prescription_id) "
        "ORDER BY rx.prescription_id DESC LIMIT %s", (int(limit),))
    return cur.fetchall()


def find_today_prescription(cur, token_number):
    cur.execute(
        "SELECT rx.prescription_id FROM Prescriptions rx "
        "JOIN Daily_Tokens t ON t.token_id = rx.token_id "
        "WHERE t.token_date = CURDATE() AND t.token_number = %s", (token_number,))
    return cur.fetchone()


# ---------------------------------------------------------------------------
# Prescription detail
# ---------------------------------------------------------------------------
def get_prescription_detail(cur, prescription_id):
    """Returns the prescription (with a 'lines' list) or None."""
    cur.execute(
        "SELECT rx.prescription_id, rx.diagnosis, rx.prescribed_at, rx.status, "
        "       t.token_number, t.token_date, (t.token_date = CURDATE()) AS is_today, "
        "       d.doctor_name, "
        "       p.patient_id, p.ar_number, p.nic_number, p.first_name, p.last_name, "
        "       p.special_conditions "
        "FROM Prescriptions rx "
        "JOIN Daily_Tokens t     ON t.token_id   = rx.token_id "
        "JOIN Students_Patients p ON p.patient_id = rx.patient_id "
        "JOIN Doctors d          ON d.doctor_id  = rx.doctor_id "
        "WHERE rx.prescription_id = %s", (prescription_id,))
    rx = cur.fetchone()
    if not rx:
        return None

    cur.execute(
        "SELECT i.item_id, m.medicine_name, m.category, i.dosage, i.quantity_given, "
        "       m.stock_quantity, m.expiry_date "
        "FROM Prescription_Items i "
        "JOIN Medicines_Inventory m ON m.medicine_id = i.medicine_id "
        "WHERE i.prescription_id = %s ORDER BY i.item_id", (prescription_id,))
    lines = cur.fetchall()
    today = date.today()
    for line in lines:
        line["stock_indicator"] = "GREEN" if line["stock_quantity"] > 0 else "RED"
        line["expired"] = bool(line["expiry_date"] and line["expiry_date"] < today)
    rx["lines"] = lines
    return rx


# ---------------------------------------------------------------------------
# Stock view
# ---------------------------------------------------------------------------
def get_stock(cur):
    cur.execute(
        "SELECT medicine_id, medicine_name, category, stock_quantity, "
        "       expiry_date, stock_indicator "
        "FROM v_medicine_stock ORDER BY medicine_name")
    medicines = cur.fetchall()
    today = date.today()
    for m in medicines:
        m["expired"] = bool(m["expiry_date"] and m["expiry_date"] < today)
    return medicines


# ---------------------------------------------------------------------------
# Dispense
# ---------------------------------------------------------------------------
def parse_packed_ids(form):
    """The item ids the pharmacist ticked as packed."""
    ids = set()
    for value in form.getlist("packed"):
        if value.isascii() and value.isdigit() and len(value) <= 9:
            ids.add(int(value))
    return ids


def dispense_prescription(prescription_id, packed_ids):
    """
    Marks the prescription Dispensed. Every medicine line must have been
    ticked as packed (checked here on the server, not just in the browser).
    The UPDATE is guarded with status = 'Pending', so two pharmacists
    pressing the button together cannot both succeed.
    Returns the token number (for the confirmation message).
    """
    with db_cursor(commit=True) as cur:
        cur.execute("SELECT status FROM Prescriptions WHERE prescription_id = %s",
                    (prescription_id,))
        rx = cur.fetchone()
        if not rx:
            raise DispenseError("Prescription not found.")
        if rx["status"] != "Pending":
            raise DispenseError("This prescription has already been dispensed.")

        cur.execute("SELECT item_id FROM Prescription_Items WHERE prescription_id = %s",
                    (prescription_id,))
        needed = {r["item_id"] for r in cur.fetchall()}
        missing = needed - packed_ids
        if missing:
            raise DispenseError(
                f"Tick every medicine as packed first ({len(missing)} still unticked).")

        cur.execute("UPDATE Prescriptions SET status = 'Dispensed' "
                    "WHERE prescription_id = %s AND status = 'Pending'",
                    (prescription_id,))
        if cur.rowcount != 1:
            raise DispenseError("This prescription has already been dispensed.")

        cur.execute("SELECT t.token_number FROM Prescriptions rx "
                    "JOIN Daily_Tokens t ON t.token_id = rx.token_id "
                    "WHERE rx.prescription_id = %s", (prescription_id,))
        token_number = cur.fetchone()["token_number"]
    return token_number
