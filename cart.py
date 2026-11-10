"""Persistent, user-owned shopping carts. Stock is checked but not reserved."""
from decimal import Decimal, ROUND_HALF_UP

from flask import Blueprint, jsonify, request, session

from db import get_db

cart = Blueprint("cart", __name__)


def cart_snapshot(database, user_id):
    rows = database.execute(
        "SELECT p.product_id, p.name, p.upc AS barcode, p.price, "
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
    except Exception:
        database.rollback()
        raise
    return jsonify(cart_snapshot(database, user_id))
