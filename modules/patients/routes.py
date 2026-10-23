"""
modules/patients/routes.py - Student self-registration, dashboard, self-issued
token, and personal medical history.
(The AI chatbot is added in Phase 7.)
"""
from flask import (Blueprint, flash, redirect, render_template, request,
                   session, url_for)
from mysql.connector import Error

from database.db_connection import db_cursor
from modules.auth.decorators import role_required
from modules.patients.history import get_patient_history
from modules.patients.services import (TokenError, issue_token,
                                       register_patient, validate_patient_form)

patients_bp = Blueprint("patients", __name__, url_prefix="/student")


@patients_bp.route("/register", methods=["GET", "POST"])
def register():
    """Public page: a student creates their own patient record + login."""
    if "user_id" in session:
        return redirect(url_for("auth.index"))

    if request.method == "GET":
        return render_template("register_student.html", form={}, errors={})

    data, errors = validate_patient_form(request.form, password_required=True)
    if not errors:
        try:
            _patient_id, errors = register_patient(data, create_account=True)
        except Error:
            flash("The database is not available. Please try again shortly.", "error")
            return render_template("register_student.html", form=data, errors={}), 503
        if not errors:
            flash("Registration successful! Log in with your AR number "
                  "and the password you chose.", "success")
            return redirect(url_for("auth.login"))

    return render_template("register_student.html", form=data, errors=errors), 400


@patients_bp.route("/dashboard")
@role_required("Student")
def dashboard():
    patient_id = session["ref_id"]
    with db_cursor() as cur:
        cur.execute(
            "SELECT patient_id, ar_number, first_name, last_name "
            "FROM Students_Patients WHERE patient_id = %s", (patient_id,))
        patient = cur.fetchone()

        # latest token issued to this student today
        cur.execute(
            "SELECT token_id, token_number, status, issued_at FROM Daily_Tokens "
            "WHERE patient_id = %s AND token_date = CURDATE() "
            "ORDER BY token_id DESC LIMIT 1", (patient_id,))
        token = cur.fetchone()

        ahead = 0
        if token and token["status"] == "Pending":
            cur.execute(
                "SELECT COUNT(*) AS n FROM Daily_Tokens "
                "WHERE token_date = CURDATE() AND token_number < %s "
                "  AND status IN ('Pending', 'In-Consultation')",
                (token["token_number"],))
            ahead = cur.fetchone()["n"]

        # after the consultation: is the medicine still at the pharmacy?
        rx_info = None
        if token and token["status"] == "Completed":
            cur.execute(
                "SELECT rx.status, "
                "       (SELECT COUNT(*) FROM Prescription_Items i "
                "         WHERE i.prescription_id = rx.prescription_id) AS n "
                "FROM Prescriptions rx WHERE rx.token_id = %s", (token["token_id"],))
            rx_info = cur.fetchone()

        cur.execute("SELECT doctor_id, doctor_name, specialization, is_available "
                    "FROM Doctors ORDER BY doctor_id")
        doctors = cur.fetchall()

    if not patient:  # profile deleted while logged in
        session.clear()
        flash("Your patient profile could not be found.", "error")
        return redirect(url_for("auth.login"))

    can_issue = token is None or token["status"] == "Completed"
    return render_template("dashboard_student.html", patient=patient,
                           token=token, ahead=ahead, can_issue=can_issue,
                           doctors=doctors, rx_info=rx_info)


@patients_bp.route("/token", methods=["POST"])
@role_required("Student")
def issue_my_token():
    """Student presses 'Get today's token' (numbers restart at 1 every day)."""
    try:
        token = issue_token(session["ref_id"])
        flash(f"Your token number for today is #{token['token_number']}.", "success")
    except TokenError as e:
        flash(str(e), "warning")
    except Error:
        flash("Could not issue a token right now. Please try again.", "error")
    return redirect(url_for("patients.dashboard"))


@patients_bp.route("/history")
@role_required("Student")
def history():
    """A student can only ever see THEIR OWN history (id comes from the session)."""
    patient_id = session["ref_id"]
    with db_cursor() as cur:
        cur.execute(
            "SELECT ar_number, first_name, last_name, special_conditions "
            "FROM Students_Patients WHERE patient_id = %s", (patient_id,))
        patient = cur.fetchone()
        records = get_patient_history(cur, patient_id, limit=100)
    return render_template("patient_history.html", patient=patient, records=records)