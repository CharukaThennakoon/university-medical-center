"""
modules/pharmacy/routes.py - Pharmacist module.

  /pharmacy/dashboard                      pending prescription queue (by token number)
  /pharmacy/find                           open a prescription by today's token number
  /pharmacy/prescription/<id>              details + packing checklist
  /pharmacy/prescription/<id>/dispense     mark as Dispensed (POST)
  /pharmacy/stock                          medicine stock levels (GREEN / RED)
"""
from flask import (Blueprint, abort, flash, redirect, render_template,
                   request, url_for)

from database.db_connection import db_cursor
from modules.auth.decorators import role_required
from modules.pharmacy.services import (DispenseError, dispense_prescription,
                                       find_today_prescription,
                                       get_dispensed_today,
                                       get_pending_queue,
                                       get_prescription_detail, get_stock,
                                       parse_packed_ids)

pharmacy_bp = Blueprint("pharmacy", __name__, url_prefix="/pharmacy")


@pharmacy_bp.route("/dashboard")
@role_required("Pharmacist")
def dashboard():
    with db_cursor() as cur:
        queue = get_pending_queue(cur)
        recent = get_dispensed_today(cur)
    pending_today = sum(1 for q in queue if q["is_today"])
    return render_template("dashboard_pharmacy.html", queue=queue, recent=recent,
                           pending_today=pending_today,
                           pending_older=len(queue) - pending_today)


@pharmacy_bp.route("/find")
@role_required("Pharmacist")
def find():
    q = request.args.get("q", "").strip()
    if not (q.isascii() and q.isdigit() and len(q) <= 9):
        flash("Enter a token number (digits only).", "warning")
        return redirect(url_for("pharmacy.dashboard"))
    with db_cursor() as cur:
        row = find_today_prescription(cur, int(q))
    if not row:
        flash(f"No prescription found for token #{q} today.", "warning")
        return redirect(url_for("pharmacy.dashboard"))
    return redirect(url_for("pharmacy.prescription", prescription_id=row["prescription_id"]))


@pharmacy_bp.route("/prescription/<int:prescription_id>")
@role_required("Pharmacist")
def prescription(prescription_id):
    with db_cursor() as cur:
        rx = get_prescription_detail(cur, prescription_id)
    if not rx:
        abort(404)
    return render_template("pharmacy_dispense.html", rx=rx)


@pharmacy_bp.route("/prescription/<int:prescription_id>/dispense", methods=["POST"])
@role_required("Pharmacist")
def dispense(prescription_id):
    try:
        token_number = dispense_prescription(prescription_id,
                                             parse_packed_ids(request.form))
    except DispenseError as e:
        flash(str(e), "warning")
        return redirect(url_for("pharmacy.prescription", prescription_id=prescription_id))
    flash(f"Token #{token_number} marked as dispensed. Hand over the medicines.", "success")
    return redirect(url_for("pharmacy.dashboard"))


@pharmacy_bp.route("/stock")
@role_required("Pharmacist")
def stock():
    with db_cursor() as cur:
        medicines = get_stock(cur)
    summary = {
        "total": len(medicines),
        "in_stock": sum(1 for m in medicines if m["stock_quantity"] > 0),
        "out_of_stock": sum(1 for m in medicines if m["stock_quantity"] == 0),
        "expired": sum(1 for m in medicines if m["expired"]),
    }
    show = request.args.get("show", "all")
    if show == "out":
        medicines = [m for m in medicines if m["stock_quantity"] == 0]
    return render_template("pharmacy_stock.html", medicines=medicines,
                           summary=summary, show=show)
