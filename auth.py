import re
import sqlite3

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db, set_active_recipient
from db import generate_membership_number
from flask import flash

auth = Blueprint("auth", __name__)


def sign_in(user):
    session.clear()
    session["user_id"] = user["user_id"]
    session["email"] = user["email"]
    session["customer_id"] = user["customer_id"]
    if user["customer_id"] is not None:
        return
    select_recipient = current_app.extensions.get("select_recipient", set_active_recipient)
    select_recipient(user["email"])


@auth.route("/signin", methods=["GET", "POST"])
def signin():
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM Users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            sign_in(user)
            if user["customer_id"] is not None:
                return redirect(url_for("account.overview"))
            return redirect(url_for("fridges"))
        error = "Email or password is incorrect."
    return render_template("signin.html", error=error)


@auth.route("/signup", methods=["GET", "POST"])
def signup():
    error = None
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            error = "Enter a valid email address."
        elif len(password) < 8:
            error = "Use a password with at least 8 characters."
        else:
            database = get_db()
            try:
                database.execute("INSERT INTO Users (email, password_hash) VALUES (?, ?)",
                                 (email, generate_password_hash(password)))
                database.commit()
            except sqlite3.IntegrityError:
                database.rollback()
                error = "An account with this email already exists."
            else:
                user = database.execute("SELECT * FROM Users WHERE email = ?", (email,)).fetchone()
                sign_in(user)
                return redirect(url_for("fridges"))
    return render_template("signup.html", error=error)

@auth.route("/customer/signup", methods=["GET", "POST"])
def customer_signup():
    if request.method == "GET":
        return render_template("customer_signup.html", error=None)

    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    address = request.form.get("address", "").strip()
    phone = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if first_name == "" or last_name == "" or address == "":
        return render_template("customer_signup.html", error="First name, last name and address are required.")
    if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        return render_template("customer_signup.html", error="Enter a valid email address.")
    if len(password) < 8:
        return render_template("customer_signup.html", error="Use a password with at least 8 characters.")
    if phone == "":
        phone = None

    password_hash = generate_password_hash(password)
    database = get_db()
    try:
        stmt = database.execute(
            "INSERT INTO Customers (first_name, last_name, address, phone, email, membership_number) VALUES (?, ?, ?, ?, ?, ?)",
            (first_name, last_name, address, phone, email, generate_membership_number(database)))
        customer_id = stmt.lastrowid
        database.execute(
            "INSERT INTO Users (email, password_hash, customer_id) VALUES (?, ?, ?)",
            (email, password_hash, customer_id))
        database.commit()
    except sqlite3.IntegrityError:
        database.rollback()
        return render_template("customer_signup.html", error="An account or customer with this email or phone number already exists.")

    stmt2 = database.execute("SELECT * FROM Users WHERE email = ?", (email,))
    sign_in(stmt2.fetchone())
    flash("Account created successfully. Welcome!", "success")
    return redirect(url_for("account.overview"))


@auth.post("/signout")
def signout():
    session.clear()
    return redirect(url_for("auth.signin"))


def init_auth(app):
    app.register_blueprint(auth)
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

    @app.before_request
    def require_signin():
        if request.endpoint == "auth.customer_signup":
            return None
        if request.endpoint in ("static", "auth.signin", "auth.signup"):
            return None
        if not session.get("user_id"):
            if request.path.startswith("/api/") or request.path == "/alerts":
                return jsonify({"error": "Please sign in."}), 401
            return redirect(url_for("auth.signin"))
        if session.get("customer_id") is not None:
            customer_pages = ["account.overview", "account.receipt", "account.email_receipt",
                                "checkout", "cart.current_cart", "cart.add_item",
                                "cart.update_item", "cart.complete_checkout",
                                "cart.scan_tags", "cart.membership", "auth.signout"]
            if request.endpoint not in customer_pages:
                if request.path.startswith("/api/") or request.path == "/alerts":
                    return jsonify({"error": "Not allowed for customer accounts."}), 403
                return redirect(url_for("account.overview"))
