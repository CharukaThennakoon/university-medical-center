"""
modules/doctor/routes.py - Doctor module (Doctor 1 and Doctor 2).

  /doctor/dashboard                 today's queue, find patient, availability
  /doctor/find                      find by Token No. or AR No.
  /doctor/consult/<token_id>        patient details, history, prescribing form
  /doctor/consult/<id>/start        Pending -> In-Consultation
  /doctor/consult/<id>/prescribe    save prescription (deducts stock, sends to pharmacy)
  /doctor/patient/<patient_id>      full patient history
  /doctor/availability              doctor toggles own availability
"""
from flask import (Blueprint, abort, flash, redirect, render_template,
                   request, session, url_for)
from mysql.connector import Error

from database.db_connection import db_cursor
from modules.auth.decorators import role_required
from modules.doctor.services import (PrescriptionError, create_prescription,
                                     get_doctors, get_token_detail,
                                     get_today_queue, list_medicines,
                                     parse_prescription_form, set_availability,
                                     start_consultation)
from modules.patients.history import (get_patient_history,
                                      get_prescription_for_token)
from modules.patients.services import find_patient_by_ar

doctor_bp = Blueprint("doctor", __name__, url_prefix="/doctor")


# ---------------------------------------------------------------------------
# Dashboard / queue / search
# ---------------------------------------------------------------------------
@doctor_bp.route("/dashboard")
@role_required("Doctor")
def dashboard():
    with db_cursor() as cur:
        queue = get_today_queue(cur)
        doctors = get_doctors(cur)

    counts = {"Pending": 0, "In-Consultation": 0, "Completed": 0}
    for t in queue:
        counts[t["status"]] += 1
    me = next((d for d in doctors if d["doctor_id"] == session["ref_id"]), None)
    return render_template("dashboard_doctor.html", queue=queue, counts=counts,
                           doctors=doctors, me=me)


@doctor_bp.route("/find")
@role_required("Doctor")
def find():
    """Identify a patient by today's Token Number or by AR Number."""
    by = request.args.get("by", "token")
    q = request.args.get("q", "").strip()
    if not q:
        return redirect(url_for("doctor.dashboard"))

    with db_cursor() as cur:
        if by == "token":
            if not (q.isascii() and q.isdigit() and len(q) <= 9):
                flash("Token number must be a number.", "warning")
                return redirect(url_for("doctor.dashboard"))
            cur.execute("SELECT token_id FROM Daily_Tokens "
                        "WHERE token_date = CURDATE() AND token_number = %s",
                        (int(q),))
            row = cur.fetchone()
            if row:
                return redirect(url_for("doctor.consult", token_id=row["token_id"]))
            flash(f"No token #{q} was issued today.", "warning")
            return redirect(url_for("doctor.dashboard"))

        patient = find_patient_by_ar(cur, q.upper())
        if not patient:
            flash(f"No patient found with AR number {q.upper()}.", "warning")
            return redirect(url_for("doctor.dashboard"))
        cur.execute("SELECT token_id FROM Daily_Tokens "
                    "WHERE patient_id = %s AND token_date = CURDATE() "
                    "ORDER BY token_id DESC LIMIT 1", (patient["patient_id"],))
        row = cur.fetchone()

    if row:
        return redirect(url_for("doctor.consult", token_id=row["token_id"]))
    flash(f"{patient['first_name']} {patient['last_name']} has no token today. "
          "Showing their history.", "info")
    return redirect(url_for("doctor.patient_history", patient_id=patient["patient_id"]))


@doctor_bp.route("/availability", methods=["POST"])
@role_required("Doctor")
def availability():
    available = request.form.get("available") == "1"
    set_availability(session["ref_id"], available)
    flash("You are now marked as available." if available
          else "You are now marked as NOT available.", "success")
    return redirect(url_for("doctor.dashboard"))


# ---------------------------------------------------------------------------
# Consultation
# ---------------------------------------------------------------------------
def _render_consult(token_id, diagnosis="", preset=None, errors=None, status=200):
    with db_cursor() as cur:
        token = get_token_detail(cur, token_id)
        if not token:
            abort(404)
        history = get_patient_history(cur, token["patient_id"], limit=10)
        prescription = (get_prescription_for_token(cur, token_id)
                        if token["status"] == "Completed" else None)
        can_prescribe = token["is_today"] and token["status"] == "In-Consultation"
        medicines = list_medicines(cur) if can_prescribe else []

    page = render_template("doctor_consult.html", token=token, history=history,
                           prescription=prescription, medicines=medicines,
                           can_prescribe=can_prescribe, diagnosis=diagnosis,
                           preset=preset or [], errors=errors or [])
    return page, status


@doctor_bp.route("/consult/<int:token_id>")
@role_required("Doctor")
def consult(token_id):
    return _render_consult(token_id)


@doctor_bp.route("/consult/<int:token_id>/start", methods=["POST"])
@role_required("Doctor")
def start(token_id):
    if not start_consultation(token_id):
        flash("This token could not be started (it is not pending, "
              "or it is not from today).", "warning")
    return redirect(url_for("doctor.consult", token_id=token_id))


@doctor_bp.route("/consult/<int:token_id>/prescribe", methods=["POST"])
@role_required("Doctor")
def prescribe(token_id):
    diagnosis, items, errors, raw_lines = parse_prescription_form(request.form)

    if not errors:
        try:
            result = create_prescription(token_id, session["ref_id"],
                                         diagnosis, items)
        except PrescriptionError as e:
            errors = [str(e)]
        except Error:
            errors = ["A database error occurred. Nothing was saved. Please try again."]
        else:
            if result["sent_to_pharmacy"]:
                flash(f"Prescription saved for Token #{result['token_number']} "
                      "and sent to the pharmacy queue.", "success")
            else:
                flash(f"Consultation for Token #{result['token_number']} saved. "
                      "No medicines were prescribed, so nothing was sent to the pharmacy.",
                      "success")
            return redirect(url_for("doctor.dashboard"))

    return _render_consult(token_id, diagnosis, raw_lines, errors, status=400)


# ---------------------------------------------------------------------------
# Patient history
# ---------------------------------------------------------------------------
@doctor_bp.route("/patient/<int:patient_id>")
@role_required("Doctor")
def patient_history(patient_id):
    with db_cursor() as cur:
        cur.execute(
            "SELECT patient_id, ar_number, nic_number, first_name, last_name, "
            "       address, height, weight, special_conditions "
            "FROM Students_Patients WHERE patient_id = %s", (patient_id,))
        patient = cur.fetchone()
        if not patient:
            abort(404)
        history = get_patient_history(cur, patient_id, limit=50)
    return render_template("doctor_patient.html", patient=patient, history=history)
