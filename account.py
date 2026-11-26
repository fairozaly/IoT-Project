import functools
from datetime import date, datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.exceptions import BadRequest

from db import get_customer, get_db
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
    # Keep links made before the portal split working.
    export = request.args.get("format")
    if export == "receipts":
        return receipt_history()
    if export == "prices" or "product_id" in request.args or "product_search" in request.args:
        return product_history()
    if "start" in request.args or "end" in request.args:
        return receipt_history()

    customer = get_customer(session["customer_id"])
    if customer is None:
        abort(404)
    return render_template("account.html", customer=customer,
                           active_page="account", account_page="membership")


@account.get("/account/receipts")
@customer_middleware
def receipt_history():
    customer_id = session["customer_id"]
    db = get_db()
    first_purchase = db.execute(
        "SELECT MIN(transaction_date) FROM Transactions "
        "WHERE customer_id = ? AND status = 'completed'", (customer_id,),
    ).fetchone()[0]
    today = datetime.now(LOCAL_TZ).date()
    first_day = date.fromisoformat(to_local(first_purchase)[:10]) if first_purchase else today
    default_start = min(first_day, today)
    export_receipts = request.args.get("format") == "receipts"
    try:
        start, end, bounds = date_range(default_start, today)
    except BadRequest as error:
        if export_receipts:
            raise
        return render_template(
            "account_receipts.html", purchases=(), date_error=error.description,
            start=request.args.get("start", default_start.isoformat()),
            end=request.args.get("end", today.isoformat()),
            active_page="account", account_page="receipts",
        ), 400

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

    if export_receipts:
        return csv_download(
            "receipts.csv",
            ("Receipt", "Purchase time (Montreal)", "Product", "Quantity", "Unit price (CAD)", "Receipt total (CAD)"),
            ((purchase["receipt_number"] or purchase["transaction_id"], to_local(purchase["transaction_date"]),
              item["name"], item["quantity"], item["price_at_sale"],
              purchase["total_amount"] if index == 0 else "")
             for purchase in purchases.values()
             for index, item in enumerate(purchase["items"] or [purchase])),
        )

    daily_spending = {}
    for purchase in purchases.values():
        day = to_local(purchase["transaction_date"])[:10]
        cents = round(purchase["total_amount"] * 100)
        daily_spending[day] = daily_spending.get(day, 0) + cents

    return render_template(
        "account_receipts.html", purchases=purchases.values(),
        total_spent=sum(daily_spending.values()) / 100,
        daily_spending=sorted(daily_spending.items()),
        start=start, end=end, active_page="account", account_page="receipts",
    )


@account.get("/account/products")
@customer_middleware
def product_history():
    customer_id = session["customer_id"]
    db = get_db()
    products = db.execute(
        """
        SELECT DISTINCT p.product_id, p.name
        FROM Transactions t JOIN TransactionItems i USING (transaction_id)
        JOIN Products p USING (product_id)
        WHERE t.customer_id = ? AND t.status = 'completed'
        ORDER BY p.name, p.product_id
        """, (customer_id,),
    ).fetchall()
    product_search = request.args.get("product_search", "").strip()
    if len(product_search) > 120:
        raise BadRequest("Product search must be 120 characters or fewer.")
    search = product_search.casefold()
    matching_products = [
        row for row in products
        if search in row["name"].casefold() or search == str(row["product_id"])
    ]
    export_prices = request.args.get("format") == "prices"
    candidates = products if export_prices else matching_products
    product_id = request.args.get("product_id", type=int)
    product = next((row for row in candidates if row["product_id"] == product_id), None)
    history = purchase_price_history(db, customer_id, product_id) if product else []
    if export_prices:
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
        "account_product_history.html",
        products=matching_products, product=product, product_search=product_search, history=history,
        purchase_count=len({row["transaction_id"] for row in history}),
        units_purchased=sum(row["quantity"] for row in history),
        active_page="account", account_page="products",
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


def receipt_filter_args():
    return {name: request.args[name] for name in ("start", "end") if name in request.args}


@account.route("/receipts/<int:transaction_id>")
@customer_middleware
def receipt(transaction_id):
    data = get_receipt(get_db(), transaction_id)
    if (
        data is None
        or data["transaction"]["customer_id"] != session["customer_id"]
        or data["transaction"]["status"] != "completed"
    ):
        abort(404)

    return render_template(
        "receipt.html", receipt=data, active_page="account", receipt_filters=receipt_filter_args(),
    )


@account.route("/receipts/<int:transaction_id>/email", methods=["POST"])
@customer_middleware
def email_receipt(transaction_id):
    db = get_db()
    data = get_receipt(db, transaction_id)
    if (
        data is None
        or data["transaction"]["customer_id"] != session["customer_id"]
        or data["transaction"]["status"] != "completed"
    ):
        abort(404)

    if send_receipt_email(db, transaction_id):
        flash("Receipt emailed successfully.", "success")
    else:
        flash("Could not email the receipt. Check your email address or try again later.", "error")
    return redirect(url_for("account.receipt", transaction_id=transaction_id, **receipt_filter_args()))
