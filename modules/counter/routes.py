"""
modules/counter/routes.py - Counter Officer: today's queue, manual patient
registration, and manual token issuing after checking Campus ID + AR number.
"""
from datetime import date

from flask import (Blueprint, abort, flash, redirect, render_template,
                   request, url_for)
from mysql.connector import Error

from database.db_connection import db_cursor
from modules.auth.decorators import role_required
from modules.patients.services import (TokenError, find_patient_by_ar,
                                       get_open_token_today, issue_token,
                                       register_patient, validate_patient_form)

counter_bp = Blueprint("counter", __name__, url_prefix="/counter")


@counter_bp.route("/dashboard")
@role_required("CounterOfficer")
def dashboard():
    with db_cursor() as cur:
        cur.execute(
            "SELECT t.token_number, t.status, t.issued_at, p.ar_number, "
            "       CONCAT(p.first_name, ' ', p.last_name) AS patient_name "
            "FROM Daily_Tokens t "
            "JOIN Students_Patients p ON p.patient_id = t.patient_id "
            "WHERE t.token_date = CURDATE() ORDER BY t.token_number")
        tokens = cur.fetchall()

    counts = {"Pending": 0, "In-Consultation": 0, "Completed": 0}
    for t in tokens:
        counts[t["status"]] += 1
    return render_template("dashboard_counter.html", tokens=tokens,
                           counts=counts, today=date.today())


@counter_bp.route("/register", methods=["GET", "POST"])
@role_required("CounterOfficer")
def register():
    """Manual registration for students who cannot self-register."""
    if request.method == "GET":
        prefill = {"ar_number": request.args.get("ar", "").strip().upper()}
        return render_template("counter_register.html", form=prefill, errors={})

    data, errors = validate_patient_form(request.form, password_required=False)
    if not errors:
        create_account = bool(data["password"])
        try:
            _patient_id, errors = register_patient(data, create_account)
        except Error:
            flash("The database is not available. Please try again shortly.", "error")
            return render_template("counter_register.html", form=data, errors={}), 503
        if not errors:
            msg = f"{data['first_name']} {data['last_name']} registered."
            if create_account:
                msg += " A login account was created (username = AR number)."
            flash(msg + " You can now issue a token.", "success")
            return redirect(url_for("counter.token", ar=data["ar_number"]))

    return render_template("counter_register.html", form=data, errors=errors), 400


@counter_bp.route("/token", methods=["GET", "POST"])
@role_required("CounterOfficer")
def token():
    """
    GET  ?ar=AR1001 : look the student up so the officer can compare the
                      Campus ID / AR number with the record.
    POST            : issue today's token (officer must tick 'ID checked').
    """
    if request.method == "POST":
        try:
            patient_id = int(request.form.get("patient_id", ""))
        except ValueError:
            abort(400)
        ar = request.form.get("ar", "").strip().upper()

        if request.form.get("id_verified") != "on":
            flash("Please confirm that the Campus ID has been checked.", "warning")
            return redirect(url_for("counter.token", ar=ar))
        try:
            issued = issue_token(patient_id)
            flash(f"Token #{issued['token_number']} issued to "
                  f"{issued['patient_name']}.", "success")
            return redirect(url_for("counter.dashboard"))
        except TokenError as e:
            flash(str(e), "warning")
        except Error:
            flash("Could not issue the token. Please try again.", "error")
        return redirect(url_for("counter.token", ar=ar))

    ar = request.args.get("ar", "").strip().upper()
    patient = open_token = None
    if ar:
        with db_cursor() as cur:
            patient = find_patient_by_ar(cur, ar)
            if patient:
                open_token = get_open_token_today(cur, patient["patient_id"])
    return render_template("counter_token.html", ar=ar, patient=patient,
                           open_token=open_token)