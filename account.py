import functools
from datetime import date, datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from db import get_db
from receipts import LOCAL_TZ, get_receipt, send_receipt_email, to_local
from reports import csv_download, date_range

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

    customer = db.execute(
        "SELECT * FROM Customers WHERE customer_id = ?", (customer_id,)
    ).fetchone()
    if customer is None:
        abort(404)

    first_purchase = db.execute(
        "SELECT MIN(transaction_date) FROM Transactions "
        "WHERE customer_id = ? AND status = 'completed'", (customer_id,),
    ).fetchone()[0]
    today = datetime.now(LOCAL_TZ).date()
    first_day = date.fromisoformat(to_local(first_purchase)[:10]) if first_purchase else today
    start, end, bounds = date_range(min(first_day, today), today)

    purchases = {}
    rows = db.execute(
        """
        SELECT t.transaction_id, t.receipt_number, t.transaction_date, t.total_amount,
               t.points_earned, p.name, i.quantity, i.price_at_sale
        FROM Transactions t LEFT JOIN TransactionItems i USING (transaction_id)
        LEFT JOIN Products p USING (product_id)
        WHERE t.customer_id = ? AND t.status = 'completed'
          AND t.transaction_date >= ? AND t.transaction_date < ?
        ORDER BY t.transaction_date DESC, t.transaction_id DESC, i.transaction_item_id
        """, (customer_id, *bounds),
    )
    for row in rows:
        purchase = purchases.setdefault(row["transaction_id"], {**dict(row), "items": []})
        if row["quantity"] is not None:
            purchase["items"].append(row)

    if request.args.get("format") == "receipts":
        return csv_download(
            "receipts.csv",
            ("Receipt", "Purchase time (Montreal)", "Product", "Quantity", "Unit price (CAD)", "Receipt total (CAD)"),
            ((purchase["receipt_number"] or purchase["transaction_id"], to_local(purchase["transaction_date"]),
              item["name"], item["quantity"], item["price_at_sale"],
              purchase["total_amount"] if index == 0 else "")
             for purchase in purchases.values()
             for index, item in enumerate(purchase["items"] or [purchase])),
        )

    products = db.execute(
        """
        SELECT DISTINCT p.product_id, p.name
        FROM Transactions t JOIN TransactionItems i USING (transaction_id)
        JOIN Products p USING (product_id)
        WHERE t.customer_id = ? AND t.status = 'completed'
        ORDER BY p.name, p.product_id
        """, (customer_id,),
    ).fetchall()
    product_id = request.args.get("product_id", type=int)
    product = next((row for row in products if row["product_id"] == product_id), None)
    history = purchase_price_history(db, customer_id, product_id) if product else []
    if request.args.get("format") == "prices":
        if product is None:
            abort(404)
        return csv_download(
            "product-price-history.csv",
            ("Product ID", "Product", "Purchase time (Montreal)", "Quantity", "Unit price (CAD)",
             "Change from previous purchase (CAD)"),
            ((product_id, product["name"], to_local(row["transaction_date"]),
              row["quantity"], row["price_at_sale"], row["change"]) for row in history),
        )
    return render_template(
        "account.html", customer=customer, purchases=purchases.values(),
        total_spent=sum(p["total_amount"] for p in purchases.values()),
        products=products, product=product, history=history,
        purchase_count=len({row["transaction_id"] for row in history}),
        units_purchased=sum(row["quantity"] for row in history),
        start=start, end=end, active_page="account",
    )


def purchase_price_history(db, customer_id, product_id):
    history = [
        dict(row) for row in db.execute(
            """
            SELECT t.transaction_id, t.transaction_date, i.quantity, i.price_at_sale
            FROM Transactions t JOIN TransactionItems i USING (transaction_id)
            WHERE t.customer_id = ? AND t.status = 'completed' AND i.product_id = ?
            ORDER BY t.transaction_date, t.transaction_id, i.transaction_item_id
            """, (customer_id, product_id),
        )
    ]
    if not history:
        return history
    low = min(row["price_at_sale"] for row in history)
    high = max(row["price_at_sale"] for row in history)
    previous = None
    for index, row in enumerate(history):
        price = row["price_at_sale"]
        row["change"] = round(price - previous, 2) if previous is not None else None
        row["x"] = 20 + (560 * index / (len(history) - 1) if len(history) > 1 else 280)
        row["y"] = 110 - (90 * (price - low) / (high - low) if high > low else 45)
        previous = price
    return history


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
