"""Shopping carts for signed-in users and guest sessions."""
import secrets
from decimal import Decimal, ROUND_HALF_UP

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for

import loyalty
import receipts
import tag_reader
from db import (
    get_customer, get_customer_by_membership_number, get_db, normalize_epc,
    record_tag_event, sync_tagged_product_quantity,
)
from validation_security import json_error

cart = Blueprint("cart", __name__)


def cart_owner():
    user_id = session.get("user_id")
    if user_id is not None:
        return "CartItems", "user_id", user_id
    cart_id = session.get("guest_cart_id")
    if cart_id is None:
        cart_id = secrets.token_urlsafe(32)
        session["guest_cart_id"] = cart_id
    return "GuestCartItems", "cart_id", cart_id


def checkout_customer():
    return get_customer(session.get("customer_id") or session.get("checkout_customer_id"))


def cart_snapshot(database, owner):
    table, column, owner_id = owner
    rows = database.execute(
        "SELECT p.product_id, p.name, p.upc AS barcode, p.price, p.image_url, "
        "CASE WHEN EXISTS (SELECT 1 FROM ProductTags t0 WHERE t0.product_id = p.product_id) "
        "THEN (SELECT COUNT(*) FROM ProductTags t1 WHERE t1.product_id = p.product_id "
        "AND t1.status = 'in_stock') ELSE p.quantity END AS stock, c.quantity "
        f"FROM {table} c "
        "JOIN Products p ON p.product_id = c.product_id "
        f"WHERE c.{column} = ? ORDER BY p.name, p.product_id", (owner_id,)
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
    owner = cart_owner()
    table, column, owner_id = owner
    if request.method == "DELETE":
        database.execute(f"DELETE FROM {table} WHERE {column} = ?", (owner_id,))
        database.commit()
        session.pop("checkout_epcs", None)
    return jsonify(cart_snapshot(database, owner))


@cart.post("/api/cart/items")
def add_item():
    return change_item()


@cart.route("/api/cart/items/<int:product_id>", methods=["PATCH", "DELETE"])
def update_item(product_id):
    return change_item(product_id)


def change_item(product_id=None):
    data = request.get_json(silent=True)
    if request.method != "DELETE" and not isinstance(data, dict):
        return json_error("Send a JSON object describing the cart change.")
    if request.method == "POST":
        allowed_keys = {"product_id", "barcode", "quantity", "epc"}
    elif request.method == "PATCH":
        allowed_keys = {"quantity"}
    else:
        allowed_keys = set()
    if isinstance(data, dict) and not data.keys() <= allowed_keys:
        return json_error("The cart request contains an unsupported field.")
    quantity = 0 if request.method == "DELETE" else data.get("quantity", 1 if product_id is None else None)
    if type(quantity) is not int or quantity < 0 or quantity > 2147483647 or (product_id is None and quantity == 0):
        return json_error("quantity must be a whole number from 1 to 2,147,483,647.")
    epc = data.get("epc") if request.method == "POST" else None
    if epc is not None:
        if quantity != 1:
            return json_error("Each scanned tag represents one unit.")
        if not isinstance(epc, str):
            return json_error("epc must be text.")
        try:
            epc = normalize_epc(epc)
        except ValueError as error:
            return json_error(str(error))
    if product_id is not None and product_id > 2**63 - 1:
        return json_error("product_id must be a positive whole number.")
    if product_id is None:
        supplied_id = data.get("product_id")
        barcode = data.get("barcode")
        if supplied_id is not None and barcode is not None:
            return json_error("Send either product_id or barcode, not both.")
        if supplied_id is not None and (type(supplied_id) is not int or not 0 < supplied_id <= 2**63 - 1):
            return json_error("product_id must be a positive whole number.")
        if supplied_id is None and (
            not isinstance(barcode, str)
            or not barcode.strip()
            or len(barcode.strip()) > 13
            or not barcode.strip().isdigit()
        ):
            return json_error("Provide a barcode containing 1 to 13 digits.")
    database = get_db()
    owner = cart_owner()
    table, column, owner_id = owner
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
                    return json_error("Unknown barcode.", 404, "not_found")
                product_id = product["product_id"]
        product = database.execute(
            "SELECT CASE WHEN EXISTS (SELECT 1 FROM ProductTags t0 WHERE t0.product_id = p.product_id) "
            "THEN (SELECT COUNT(*) FROM ProductTags t1 WHERE t1.product_id = p.product_id "
            "AND t1.status = 'in_stock') ELSE p.quantity END AS quantity "
            "FROM Products p WHERE p.product_id = ?", (product_id,)
        ).fetchone()
        if product is None:
            database.rollback()
            return json_error("Product not found.", 404, "not_found")
        existing = database.execute(f"SELECT quantity FROM {table} WHERE {column} = ? AND product_id = ?", (owner_id, product_id)).fetchone()
        scanned = session.get("checkout_epcs") or {}
        scanned_key = str(product_id)
        values = scanned.get(scanned_key, [])
        if epc is not None:
            if database.execute(
                "SELECT 1 FROM ProductTags WHERE product_id = ? AND epc = ? "
                "AND status = 'in_stock'",
                (product_id, epc),
            ).fetchone() is None:
                database.rollback()
                return json_error("That RFID tag is no longer in stock for this product.", 409, "stale_resource")
            if existing and epc in values:
                database.rollback()
                return jsonify(cart_snapshot(database, owner))
        if request.method == "POST":
            quantity += existing["quantity"] if existing else 0
        if quantity > product["quantity"]:
            database.rollback()
            return json_error("Not enough stock available.", 409, "stock_conflict", stock=product["quantity"])
        if quantity == 0:
            database.execute(f"DELETE FROM {table} WHERE {column} = ? AND product_id = ?", (owner_id, product_id))
        else:
            database.execute(
                f"INSERT INTO {table} ({column}, product_id, quantity) VALUES (?, ?, ?) "
                f"ON CONFLICT({column}, product_id) DO UPDATE SET quantity = excluded.quantity",
                (owner_id, product_id, quantity))
        database.commit()
        if epc is not None:
            scanned[scanned_key] = [*values, epc]
            session["checkout_epcs"] = scanned
        elif request.method != "POST" and quantity < len(values):
            if quantity:
                scanned[scanned_key] = values[:quantity]
            else:
                scanned.pop(scanned_key, None)
            session["checkout_epcs"] = scanned
    except Exception:
        database.rollback()
        raise
    return jsonify(cart_snapshot(database, owner))


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
            "WHERE t.epc = ? AND t.status = 'in_stock'", (epc,)
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
    if session.get("customer_id") is not None:
        return json_error(
            "Your signed-in membership is applied automatically.",
            403,
            "membership_forbidden",
        )
    if request.method == "DELETE":
        session.pop("checkout_customer_id", None)
        session.pop("checkout_membership_number", None)
        return jsonify(applied=False)

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return json_error("Send a JSON object containing membership or membership_number.")
    if not data.keys() <= {"membership", "membership_number"}:
        return json_error("The membership request contains an unsupported field.")
    if "membership" in data and "membership_number" in data:
        return json_error("Send either membership or membership_number, not both.")
    identifier = data.get("membership", data.get("membership_number"))
    if not isinstance(identifier, str) or not identifier.strip() or len(identifier.strip()) > 64:
        return json_error("Scan or enter a membership number.")
    identifier = identifier.strip()
    customer = get_customer_by_membership_number(identifier)
    if customer is None:
        return json_error("Membership not found.", 404, "not_found")
    session["checkout_customer_id"] = customer["customer_id"]
    return jsonify(applied=True)


@cart.post("/checkout/complete")
def complete_checkout():
    database = get_db()
    table, column, owner_id = cart_owner()

    try:
        database.execute("BEGIN IMMEDIATE")
        customer = checkout_customer()
        customer_id = customer["customer_id"] if customer else None
        rows = database.execute(
            "SELECT p.product_id, p.price, p.cost_price, p.taxable, "
            "EXISTS (SELECT 1 FROM ProductTags t2 WHERE t2.product_id = p.product_id) AS tagged_inventory, "
            "CASE WHEN EXISTS (SELECT 1 FROM ProductTags t0 WHERE t0.product_id = p.product_id) "
            "THEN (SELECT COUNT(*) FROM ProductTags t1 WHERE t1.product_id = p.product_id "
            "AND t1.status = 'in_stock') ELSE p.quantity END AS stock, c.quantity "
            f"FROM {table} c JOIN Products p ON p.product_id = c.product_id "
            f"WHERE c.{column} = ?", (owner_id,),
        ).fetchall()
        if not rows:
            database.rollback()
            flash("Your cart is empty.", "error")
            return redirect(url_for("checkout"))

        if any(item["quantity"] > item["stock"] for item in rows):
            database.rollback()
            flash("Some items are no longer in stock. Update your cart and try again.", "error")
            return redirect(url_for("checkout"))

        totals = receipts.calculate_totals(rows)

        transaction = database.execute(
            "INSERT INTO Transactions (customer_id, total_amount, subtotal_amount, gst_amount, "
            "qst_amount, tax_amount, cost_amount, profit_amount, gst_rate, qst_rate, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed')",
            (customer_id, float(totals["total"]), float(totals["subtotal"]),
             float(totals["gst"]), float(totals["qst"]), float(totals["tax"]),
             float(totals["cost"]), float(totals["profit"]), float(totals["gst_rate"]),
             float(totals["qst_rate"])),
        )
        transaction_id = transaction.lastrowid

        scanned = session.get("checkout_epcs") or {}
        for item in rows:
            database.execute(
                "INSERT INTO TransactionItems "
                "(transaction_id, product_id, quantity, price_at_sale, cost_at_sale, taxable_at_sale) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (transaction_id, item["product_id"], item["quantity"], item["price"],
                 item["cost_price"], item["taxable"]))
            if not item["tagged_inventory"]:
                database.execute(
                    "UPDATE Products SET quantity = quantity - ? WHERE product_id = ?",
                    (item["quantity"], item["product_id"]))
                continue
            epcs = list(scanned.get(str(item["product_id"]), [])[:item["quantity"]])
            remaining = item["quantity"] - len(epcs)
            if remaining:
                excluded = ""
                params = [item["product_id"]]
                if epcs:
                    excluded = " AND epc NOT IN (" + ",".join("?" for _ in epcs) + ")"
                    params.extend(epcs)
                params.append(remaining)
                available_tags = database.execute(
                    "SELECT tag_id, epc FROM ProductTags WHERE product_id = ? "
                    "AND status = 'in_stock'" + excluded + " ORDER BY tag_id LIMIT ?",
                    params,
                ).fetchall()
                if len(available_tags) != remaining:
                    database.rollback()
                    flash("A scanned RFID tag is no longer in stock. Clear the cart and scan your items again.", "error")
                    return redirect(url_for("checkout"))
                epcs.extend(tag["epc"] for tag in available_tags)
            if epcs:
                for epc in epcs:
                    updated = database.execute(
                        "UPDATE ProductTags SET status = 'sold', sold_at = CURRENT_TIMESTAMP, "
                        "transaction_id = ?, removed_at = NULL WHERE product_id = ? "
                        "AND epc = ? AND status = 'in_stock'",
                        (transaction_id, item["product_id"], epc),
                    )
                    if updated.rowcount != 1:
                        database.rollback()
                        flash("A scanned RFID tag is no longer in stock. Clear the cart and scan your items again.", "error")
                        return redirect(url_for("checkout"))
                    tag_id = database.execute(
                        "SELECT tag_id FROM ProductTags WHERE product_id = ? AND epc = ?",
                        (item["product_id"], epc),
                    ).fetchone()["tag_id"]
                    record_tag_event(database, tag_id, "sold", transaction_id=transaction_id,
                                     note="Sold at checkout")
                sync_tagged_product_quantity(database, item["product_id"])

        database.execute(
            "INSERT INTO PaymentMethods (transaction_id, method, amount) "
            "VALUES (?, 'pay_now', ?)", (transaction_id, float(totals["total"])))
        database.execute(f"DELETE FROM {table} WHERE {column} = ?", (owner_id,))

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
    session["checkout_receipt_id"] = transaction_id
    return redirect(url_for("cart.guest_receipt", transaction_id=transaction_id))


@cart.get("/checkout/receipt/<int:transaction_id>")
def guest_receipt(transaction_id):
    if transaction_id != session.get("checkout_receipt_id"):
        abort(404)
    data = receipts.get_receipt(get_db(), transaction_id)
    if data is None:
        abort(404)
    return render_template("receipt.html", receipt=data, checkout_receipt=True,
                           active_page="checkout"), 200, {"Cache-Control": "private, no-store"}
