"""Persistent, user-owned shopping carts. Stock is checked but not reserved."""
from decimal import Decimal, ROUND_HALF_UP

from flask import Blueprint, current_app, flash, jsonify, redirect, request, session, url_for

import loyalty
import receipts
import tag_reader
from db import get_customer_by_membership_number, get_db, normalize_epc

cart = Blueprint("cart", __name__)


def cart_snapshot(database, user_id):
    rows = database.execute(
        "SELECT p.product_id, p.name, p.upc AS barcode, p.price, p.image_url, "
        "p.quantity AS stock, c.quantity FROM CartItems c "
        "JOIN Products p ON p.product_id = c.product_id "
        "WHERE c.user_id = ? ORDER BY p.name, p.product_id", (user_id,)
    ).fetchall()
    items = []
    total = Decimal("0.00")
    for row in rows:
        item = dict(row)
        price = Decimal(str(item["price"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        subtotal = price * item["quantity"]
        item.update(price=float(price), subtotal=float(subtotal),
                    available=item["quantity"] <= item["stock"])
        total += subtotal
        items.append(item)
    return {"items": items, "total": float(total),
            "quantity": sum(item["quantity"] for item in items),
            "stock_available": all(item["available"] for item in items)}


@cart.route("/api/cart", methods=["GET", "DELETE"])
def current_cart():
    database = get_db()
    user_id = session["user_id"]
    if request.method == "DELETE":
        database.execute("DELETE FROM CartItems WHERE user_id = ?", (user_id,))
        database.commit()
        session.pop("checkout_epcs", None)
    return jsonify(cart_snapshot(database, user_id))


@cart.post("/api/cart/items")
def add_item():
    return change_item()


@cart.route("/api/cart/items/<int:product_id>", methods=["PATCH", "DELETE"])
def update_item(product_id):
    return change_item(product_id)


def change_item(product_id=None):
    data = request.get_json(silent=True)
    if request.method != "DELETE" and not isinstance(data, dict):
        return jsonify(error="Send a JSON object."), 400
    quantity = 0 if request.method == "DELETE" else data.get("quantity", 1 if product_id is None else None)
    if type(quantity) is not int or quantity < 0 or quantity > 2147483647 or (product_id is None and quantity == 0):
        return jsonify(error="Quantity must be a valid whole number."), 400
    epc = data.get("epc") if request.method == "POST" else None
    if epc is not None:
        if not isinstance(epc, str):
            return jsonify(error="Invalid EPC."), 400
        try:
            epc = normalize_epc(epc)
        except ValueError as error:
            return jsonify(error=str(error)), 400
    if product_id is None:
        supplied_id = data.get("product_id")
        barcode = data.get("barcode")
        if supplied_id is not None and (type(supplied_id) is not int or supplied_id <= 0):
            return jsonify(error="Invalid product ID."), 400
        if supplied_id is None and (not isinstance(barcode, str) or not barcode.strip() or len(barcode) > 13):
            return jsonify(error="Provide a product ID or valid barcode."), 400
    database = get_db()
    user_id = session["user_id"]
    try:
        # Serialize read/check/write so concurrent scans cannot lose increments.
        database.execute("BEGIN IMMEDIATE")
        if product_id is None:
            if supplied_id is not None:
                product_id = supplied_id
            else:
                product = database.execute("SELECT product_id FROM Products WHERE upc = ?", (barcode.strip(),)).fetchone()
                if product is None:
                    database.rollback()
                    return jsonify(error="Unknown barcode."), 404
                product_id = product["product_id"]
        product = database.execute("SELECT quantity FROM Products WHERE product_id = ?", (product_id,)).fetchone()
        if product is None:
            database.rollback()
            return jsonify(error="Product not found."), 404
        existing = database.execute("SELECT quantity FROM CartItems WHERE user_id = ? AND product_id = ?", (user_id, product_id)).fetchone()
        if request.method == "POST":
            quantity += existing["quantity"] if existing else 0
        if quantity > product["quantity"]:
            database.rollback()
            return jsonify(error="Not enough stock available.", stock=product["quantity"]), 409
        if quantity == 0:
            database.execute("DELETE FROM CartItems WHERE user_id = ? AND product_id = ?", (user_id, product_id))
        else:
            database.execute(
                "INSERT INTO CartItems (user_id, product_id, quantity) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id, product_id) DO UPDATE SET quantity = excluded.quantity",
                (user_id, product_id, quantity))
        database.commit()
        if epc is not None:
            scanned = session.get("checkout_epcs") or {}
            values = list(scanned.get(str(product_id), []))
            if epc not in values:
                values.append(epc)
            scanned[str(product_id)] = values
            session["checkout_epcs"] = scanned
    except Exception:
        database.rollback()
        raise
    return jsonify(cart_snapshot(database, user_id))


@cart.get("/api/checkout/tags")
def scan_tags():
    if current_app.config.get("START_SERVICES", True):
        tag_reader.ensure_started()
    database = get_db()
    results = []
    for epc in tag_reader.get_tags():
        product = database.execute(
            "SELECT p.product_id, p.name, p.price, p.quantity AS stock, p.image_url "
            "FROM Products p JOIN ProductTags t ON t.product_id = p.product_id "
            "WHERE t.epc = ?", (epc,)
        ).fetchone()
        results.append({
            "epc": epc,
            "product": dict(product) if product is not None else None,
        })
    return jsonify(
        connected=tag_reader.is_connected(),
        error=tag_reader.get_last_error(),
        results=results,
    )


@cart.route("/api/checkout/membership", methods=["POST", "DELETE"])
def membership():
    if request.method == "DELETE":
        session.pop("checkout_customer_id", None)
        session.pop("checkout_membership_number", None)
        session.pop("checkout_epcs", None)
        return jsonify(customer=None)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Send a JSON object."), 400
    number = data.get("membership_number")
    if not isinstance(number, str) or not number.strip():
        return jsonify(error="Scan or enter a membership number."), 400
    customer = get_customer_by_membership_number(number)
    if customer is None:
        return jsonify(error="Membership number not found."), 404
    session_customer_id = session.get("customer_id")
    if session_customer_id is not None and session_customer_id != customer["customer_id"]:
        return jsonify(error="This membership belongs to another customer."), 403
    session["checkout_customer_id"] = customer["customer_id"]
    session["checkout_membership_number"] = customer["membership_number"]
    return jsonify(customer=dict(customer))


@cart.post("/checkout/complete")
def complete_checkout():
    database = get_db()
    user_id = session["user_id"]
    customer_id = session.get("checkout_customer_id")

    rows = database.execute(
        "SELECT p.product_id, p.price, p.quantity AS stock, c.quantity "
        "FROM CartItems c JOIN Products p ON p.product_id = c.product_id "
        "WHERE c.user_id = ?", (user_id,)
    ).fetchall()
    if not rows:
        flash("Your cart is empty.", "error")
        return redirect(url_for("checkout"))

    if any(item["quantity"] > item["stock"] for item in rows):
        flash("Some items are no longer in stock. Update your cart and try again.", "error")
        return redirect(url_for("checkout"))

    if customer_id is None:
        flash("Scan your membership before paying.", "error")
        return redirect(url_for("checkout"))

    total = sum(
        Decimal(str(item["price"])) * item["quantity"] for item in rows
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    try:
        database.execute("BEGIN IMMEDIATE")
        transaction = database.execute(
            "INSERT INTO Transactions (customer_id, total_amount, status) "
            "VALUES (?, ?, 'completed')", (customer_id, float(total))
        )
        transaction_id = transaction.lastrowid

        for item in rows:
            database.execute(
                "INSERT INTO TransactionItems "
                "(transaction_id, product_id, quantity, price_at_sale) "
                "VALUES (?, ?, ?, ?)",
                (transaction_id, item["product_id"], item["quantity"], item["price"]))
            database.execute(
                "UPDATE Products SET quantity = quantity - ? WHERE product_id = ?",
                (item["quantity"], item["product_id"]))
            scanned = session.get("checkout_epcs") or {}
            remaining = item["quantity"]
            for epc in scanned.get(str(item["product_id"]), [])[:item["quantity"]]:
                remaining -= database.execute(
                    "DELETE FROM ProductTags WHERE product_id = ? AND epc = ?",
                    (item["product_id"], epc),
                ).rowcount
            if remaining > 0:
                database.execute(
                    "DELETE FROM ProductTags WHERE tag_id IN ("
                    "SELECT tag_id FROM ProductTags WHERE product_id = ? "
                    "ORDER BY tag_id LIMIT ?)",
                    (item["product_id"], remaining))

        database.execute(
            "INSERT INTO PaymentMethods (transaction_id, method, amount) "
            "VALUES (?, 'pay_now', ?)", (transaction_id, float(total)))
        database.execute("DELETE FROM CartItems WHERE user_id = ?", (user_id,))

        receipt_number = receipts.assign_receipt_number(database, transaction_id)
        points = loyalty.award_points(database, transaction_id)
        database.commit()
        session.pop("checkout_customer_id", None)
        session.pop("checkout_membership_number", None)
        session.pop("checkout_epcs", None)
    except Exception:
        database.rollback()
        raise

    try:
        emailed = receipts.send_receipt_email(database, transaction_id)
    except Exception:
        emailed = False
    message = f"Checkout complete. Receipt {receipt_number}."
    if customer_id is not None:
        message += f" You earned {points} point(s)."
    if emailed:
        message += " The receipt was emailed."
    flash(message, "success")

    if session.get("customer_id") is not None:
        return redirect(url_for("account.receipt", transaction_id=transaction_id))
    return redirect(url_for("checkout"))
