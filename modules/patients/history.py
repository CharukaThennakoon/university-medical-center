"""
modules/patients/history.py - Prescription history queries.

Used by the doctor module now, and by the student's "My Medical History"
page in Phase 6.

NOTE: each prescription's medicine lines are stored under the key
'medicines' (not 'items', which would clash with dict.items() in Jinja).
"""


def _attach_medicines(cur, rows):
    """Adds row['medicines'] = [{medicine_name, dosage, quantity_given}, ...]."""
    if not rows:
        return rows
    ids = [r["prescription_id"] for r in rows]
    placeholders = ", ".join(["%s"] * len(ids))  # one %s per id (not user text)
    cur.execute(
        "SELECT i.prescription_id, m.medicine_name, i.dosage, i.quantity_given "
        "FROM Prescription_Items i "
        "JOIN Medicines_Inventory m ON m.medicine_id = i.medicine_id "
        f"WHERE i.prescription_id IN ({placeholders}) ORDER BY i.item_id", ids)
    by_rx = {}
    for line in cur.fetchall():
        by_rx.setdefault(line["prescription_id"], []).append(line)
    for r in rows:
        r["medicines"] = by_rx.get(r["prescription_id"], [])
    return rows


_BASE = (
    "SELECT rx.prescription_id, rx.token_id, rx.diagnosis, rx.prescribed_at, "
    "       rx.status, d.doctor_name, t.token_number "
    "FROM Prescriptions rx "
    "JOIN Doctors d      ON d.doctor_id = rx.doctor_id "
    "JOIN Daily_Tokens t ON t.token_id  = rx.token_id "
)


def get_patient_history(cur, patient_id, limit=50):
    """Newest first. Each row has a 'medicines' list."""
    cur.execute(
        _BASE + "WHERE rx.patient_id = %s "
        "ORDER BY rx.prescribed_at DESC, rx.prescription_id DESC LIMIT %s",
        (patient_id, int(limit)))
    return _attach_medicines(cur, cur.fetchall())


def get_prescription_for_token(cur, token_id):
    cur.execute(_BASE + "WHERE rx.token_id = %s", (token_id,))
    rows = _attach_medicines(cur, cur.fetchall())
    return rows[0] if rows else None
