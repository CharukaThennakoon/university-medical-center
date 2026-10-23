"""
modules/admin/routes.py - Administrator module (role: Admin).

  /admin/dashboard                  overview + stock alerts
  /admin/users                      list, create staff login, reset password, (de)activate
  /admin/doctors                    add doctor (+ login), edit, availability
  /admin/medicines                  add / edit medicines, restock, stock-take correction
  /admin/patients[/<id>]            search, fix name / address
  /admin/reports                    visits per day, top medicines, doctor workload
  /admin/audit                      what every admin changed

Every POST form carries the CSRF token (checked for the whole app in app.py).
Validation problems are shown as a flash message and the page reloads.
"""
from datetime import date

from flask import (Blueprint, abort, flash, redirect, render_template,
                   request, session, url_for)
from mysql.connector import Error

from database.db_connection import db_cursor
from modules.admin import services as svc
from modules.auth.decorators import role_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

_DB_ERROR = "A database error occurred. Nothing was changed. Please try again."


def _actor():
    return {"user_id": session["user_id"], "username": session["username"]}


def _run(action, success, back, **back_kwargs):
    """
    Runs a service call that returns a list of error messages (or raises).
    Shows `success` when it worked, the problems otherwise, then redirects.
    """
    try:
        errors = action()
    except svc.AdminError as e:
        flash(str(e), "warning")
    except Error:
        flash(_DB_ERROR, "error")
    else:
        if errors:
            flash(" ".join(errors), "warning")
        else:
            flash(success, "success")
    return redirect(url_for(back, **back_kwargs))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@admin_bp.route("/dashboard")
@role_required("Admin")
def dashboard():
    with db_cursor() as cur:
        stats = svc.get_dashboard_stats(cur)
    return render_template("dashboard_admin.html", s=stats, today=date.today(),
                           low_stock=svc.LOW_STOCK)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
@admin_bp.route("/users")
@role_required("Admin")
def users():
    q = request.args.get("q", "").strip()[:50]
    with db_cursor() as cur:
        rows = svc.list_users(cur, q)
    return render_template("admin_users.html", users=rows, q=q,
                           staff_roles=svc.STAFF_ROLES, me=session["user_id"])


@admin_bp.route("/users/create", methods=["POST"])
@role_required("Admin")
def create_user():
    return _run(lambda: svc.create_staff_user(_actor(), request.form),
                "Account created.", "admin.users")


@admin_bp.route("/users/<int:user_id>/reset-password", methods=["POST"])
@role_required("Admin")
def reset_password(user_id):
    try:
        name = svc.reset_password(_actor(), user_id, request.form)
        flash(f"Password for '{name}' was changed.", "success")
    except svc.AdminError as e:
        flash(str(e), "warning")
    except Error:
        flash(_DB_ERROR, "error")
    return redirect(url_for("admin.users", q=request.form.get("q", "")))


@admin_bp.route("/users/<int:user_id>/active", methods=["POST"])
@role_required("Admin")
def toggle_user(user_id):
    active = request.form.get("active") == "1"
    try:
        name = svc.set_user_active(_actor(), user_id, active)
        flash(f"Account '{name}' {'activated' if active else 'deactivated'}.", "success")
    except svc.AdminError as e:
        flash(str(e), "warning")
    except Error:
        flash(_DB_ERROR, "error")
    return redirect(url_for("admin.users", q=request.form.get("q", "")))


# ---------------------------------------------------------------------------
# Doctors
# ---------------------------------------------------------------------------
@admin_bp.route("/doctors")
@role_required("Admin")
def doctors():
    with db_cursor() as cur:
        rows = svc.list_doctors(cur)
    return render_template("admin_doctors.html", doctors=rows)


@admin_bp.route("/doctors/create", methods=["POST"])
@role_required("Admin")
def create_doctor():
    return _run(lambda: svc.create_doctor(_actor(), request.form),
                "Doctor and login account created.", "admin.doctors")


@admin_bp.route("/doctors/<int:doctor_id>/update", methods=["POST"])
@role_required("Admin")
def update_doctor(doctor_id):
    return _run(lambda: svc.update_doctor(_actor(), doctor_id, request.form),
                "Doctor updated.", "admin.doctors")


# ---------------------------------------------------------------------------
# Medicines
# ---------------------------------------------------------------------------
@admin_bp.route("/medicines")
@role_required("Admin")
def medicines():
    q = request.args.get("q", "").strip()[:100]
    show = "attention" if request.args.get("show") == "attention" else "all"
    with db_cursor() as cur:
        rows = svc.list_medicines(cur, q, show)
    return render_template("admin_medicines.html", medicines=rows, q=q, show=show,
                           low_stock=svc.LOW_STOCK, warn_days=svc.EXPIRY_WARN_DAYS)


@admin_bp.route("/medicines/create", methods=["POST"])
@role_required("Admin")
def create_medicine():
    return _run(lambda: svc.create_medicine(_actor(), request.form),
                "Medicine added.", "admin.medicines")


@admin_bp.route("/medicines/<int:medicine_id>/update", methods=["POST"])
@role_required("Admin")
def update_medicine(medicine_id):
    return _run(lambda: svc.update_medicine(_actor(), medicine_id, request.form),
                "Medicine updated.", "admin.medicines",
                q=request.form.get("q", ""), show=request.form.get("show", "all"))


@admin_bp.route("/medicines/<int:medicine_id>/stock", methods=["POST"])
@role_required("Admin")
def stock(medicine_id):
    try:
        name, old, new = svc.adjust_stock(_actor(), medicine_id,
                                          request.form.get("mode", ""),
                                          request.form.get("quantity", ""))
        flash(f"{name}: stock {old} \u2192 {new}.", "success")
    except svc.AdminError as e:
        flash(str(e), "warning")
    except Error:
        flash(_DB_ERROR, "error")
    return redirect(url_for("admin.medicines", q=request.form.get("q", ""),
                            show=request.form.get("show", "all")))


# ---------------------------------------------------------------------------
# Patients
# ---------------------------------------------------------------------------
@admin_bp.route("/patients")
@role_required("Admin")
def patients():
    q = request.args.get("q", "").strip()[:50]
    with db_cursor() as cur:
        rows = svc.list_patients(cur, q)
    return render_template("admin_patients.html", patients=rows, q=q)


@admin_bp.route("/patients/<int:patient_id>", methods=["GET", "POST"])
@role_required("Admin")
def patient_edit(patient_id):
    if request.method == "POST":
        try:
            data, errors = svc.update_patient(_actor(), patient_id, request.form)
        except svc.AdminError:
            abort(404)
        except Error:
            flash(_DB_ERROR, "error")
            return redirect(url_for("admin.patient_edit", patient_id=patient_id))
        if not errors:
            flash("Patient details updated.", "success")
            return redirect(url_for("admin.patients"))
        with db_cursor() as cur:
            patient = svc.get_patient(cur, patient_id)
        if not patient:
            abort(404)
        return render_template("admin_patient_edit.html", patient=patient,
                               form=data, errors=errors), 400

    with db_cursor() as cur:
        patient = svc.get_patient(cur, patient_id)
    if not patient:
        abort(404)
    return render_template("admin_patient_edit.html", patient=patient,
                           form=patient, errors={})


# ---------------------------------------------------------------------------
# Reports + audit
# ---------------------------------------------------------------------------
@admin_bp.route("/reports")
@role_required("Admin")
def reports():
    with db_cursor() as cur:
        visits = svc.visits_per_day(cur, 14)
        medicines = svc.top_medicines(cur, 30)
        workload = svc.doctor_workload(cur, 30)
    peak = max([v["total"] for v in visits], default=1)
    return render_template("admin_reports.html", visits=visits, peak=peak,
                           medicines=medicines, workload=workload)


@admin_bp.route("/audit")
@role_required("Admin")
def audit():
    with db_cursor() as cur:
        rows = svc.list_audit(cur)
    return render_template("admin_audit.html", rows=rows)
