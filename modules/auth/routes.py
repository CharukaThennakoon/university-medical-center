"""
modules/auth/routes.py - Login / logout and role-based redirect.
"""
from urllib.parse import urlparse

from flask import (Blueprint, flash, redirect, render_template, request,
                   session, url_for)
from mysql.connector import Error
from werkzeug.security import check_password_hash, generate_password_hash

from database.db_connection import db_cursor

auth_bp = Blueprint("auth", __name__)

# Where each role lands after login (endpoint = blueprint.function)
ROLE_HOME = {
    "Student": "patients.dashboard",
    "Doctor": "doctor.dashboard",
    "Pharmacist": "pharmacy.dashboard",
    "CounterOfficer": "counter.dashboard",
    "Admin": "admin.dashboard",
}

# Checked when the username does not exist, so a wrong username and a wrong
# password take about the same time (prevents username guessing by timing).
_DUMMY_HASH = generate_password_hash("not-a-real-password")


def _safe_next(target):
    """Allow only same-site relative paths (blocks open-redirect attacks)."""
    if not target:
        return None
    parts = urlparse(target)
    if (parts.scheme or parts.netloc or not target.startswith("/")
            or target.startswith("//") or "\\" in target):
        return None
    return target


def _load_display_name(cur, role, ref_id):
    """
    Users_Roles.ref_id is polymorphic (no real foreign key), so the link is
    verified here in the application layer. Returns None if it is broken.
    """
    if role == "Student":
        cur.execute(
            "SELECT CONCAT(first_name, ' ', last_name) AS name "
            "FROM Students_Patients WHERE patient_id = %s", (ref_id,))
    elif role == "Doctor":
        cur.execute(
            "SELECT doctor_name AS name FROM Doctors WHERE doctor_id = %s",
            (ref_id,))
    elif role == "Pharmacist":
        return "Pharmacist"
    elif role == "CounterOfficer":
        return "Counter Officer"
    elif role == "Admin":
        return "Administrator"
    else:
        return None
    row = cur.fetchone()
    return row["name"] if row else None


@auth_bp.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for(ROLE_HOME[session["role"]]))
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for(ROLE_HOME[session["role"]]))

    if request.method == "GET":
        return render_template("login.html",
                               next_url=_safe_next(request.args.get("next")))

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    next_url = _safe_next(request.form.get("next"))

    try:
        with db_cursor() as cur:
            cur.execute(
                "SELECT user_id, username, password_hash, role, ref_id, is_active "
                "FROM Users_Roles WHERE username = %s", (username,))
            user = cur.fetchone()
            name = (_load_display_name(cur, user["role"], user["ref_id"])
                    if user else None)
    except Error:
        flash("The database is not available. Is MySQL running in XAMPP?",
              "error")
        return render_template("login.html", next_url=next_url), 503

    hash_to_check = user["password_hash"] if user else _DUMMY_HASH
    password_ok = check_password_hash(hash_to_check, password)

    if not (user and password_ok):
        flash("Invalid username or password.", "error")
        return render_template("login.html", next_url=next_url), 401

    if not user["is_active"]:
        flash("This account has been deactivated. Please contact the administrator.",
              "error")
        return render_template("login.html", next_url=next_url), 403

    if name is None:
        flash("This account is not linked to a profile. "
              "Please contact the counter officer.", "error")
        return render_template("login.html", next_url=next_url), 403

    session.clear()  # drop any old session data (prevents session fixation)
    session.permanent = True
    session.update(
        user_id=user["user_id"],
        username=user["username"],
        role=user["role"],
        ref_id=user["ref_id"],
        display_name=name,
    )
    flash(f"Welcome, {name}!", "success")
    return redirect(next_url or url_for(ROLE_HOME[user["role"]]))


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
