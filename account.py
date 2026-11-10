import functools

from flask import Blueprint, abort, flash, redirect, render_template, session, url_for

from db import get_db
from receipts import get_receipt, send_receipt_email, to_local

account = Blueprint("account", __name__)
account.add_app_template_filter(to_local, "localtime")


def customer_middleware(view):
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if session.get("customer_id") is None:
            flash("That page is for customer accounts.", "error")
            return redirect(url_for("fridges"))
        return view(*args, **kwargs)
    return wrapper


@account.route("/account")
@customer_middleware
def overview():
    customer_id = session["customer_id"]
    db = get_db()

    stmt = db.execute("SELECT first_name, last_name, email, phone, address, membership_number, total_points FROM Customers WHERE customer_id = ?", (customer_id,))
    customer = stmt.fetchone()

    stmt2 = db.execute("SELECT transaction_id, receipt_number, transaction_date, total_amount, points_earned FROM Transactions WHERE customer_id = ? ORDER BY transaction_date DESC, transaction_id DESC", (customer_id,))
    purchases = stmt2.fetchall()

    return render_template("account.html", customer=customer, purchases=purchases, active_page="account")


@account.route("/receipts/<int:transaction_id>")
@customer_middleware
def receipt(transaction_id):
    data = get_receipt(get_db(), transaction_id)
    if data is None or data["transaction"]["customer_id"] != session["customer_id"]:
        abort(404)

    return render_template("receipt.html", receipt=data, active_page="account")


@account.route("/receipts/<int:transaction_id>/email", methods=["POST"])
@customer_middleware
def email_receipt(transaction_id):
    db = get_db()
    data = get_receipt(db, transaction_id)
    if data is None or data["transaction"]["customer_id"] != session["customer_id"]:
        abort(404)

    if send_receipt_email(db, transaction_id):
        flash("Receipt emailed successfully.", "success")
    else:
        flash("Could not email the receipt. Check your email address or try again later.", "error")
    return redirect(url_for("account.receipt", transaction_id=transaction_id))
