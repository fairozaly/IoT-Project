import sqlite3

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db, set_active_recipient
from flask import flash
from validation_security import (
    expose_csrf,
    get_csrf_token,
    normalize_quebec_phone,
    valid_email,
    valid_phone,
    validate_csrf_request,
)

auth = Blueprint("auth", __name__)
PASSWORD_HASH_METHOD = "pbkdf2:sha256:600000"


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
        if len(email) > 254 or len(password) > 128:
            return render_template("signin.html", error="Email or password is incorrect."), 400
        user = get_db().execute("SELECT * FROM Users WHERE email = ?", (email,)).fetchone()
        try:
            password_matches = bool(user and check_password_hash(user["password_hash"], password))
        except (TypeError, ValueError):
            password_matches = False
        if password_matches:
            sign_in(user)
            if user["customer_id"] is not None:
                return redirect(url_for("account.overview"))
            return redirect(url_for("fridges"))
        error = "Email or password is incorrect."
    return render_template("signin.html", error=error)


@auth.route("/signup", methods=["GET", "POST"])
def signup():
    """Retain the old URL without allowing public staff-account creation.

    Operations accounts are provisioned outside the application UI.  Keeping
    this redirect avoids a dead link for bookmarked or previously shared URLs,
    while ensuring that neither GET nor POST can create a new operations user.
    """
    return redirect(url_for("auth.signin"))


@auth.get("/api/csrf-token")
def csrf_token():
    """Return a token for API clients using the explicit CSRF header contract."""
    return jsonify(csrf_token=get_csrf_token())

@auth.route("/customer/signup", methods=["GET", "POST"])
def customer_signup():
    if request.method == "GET":
        return render_template("customer_signup.html", error=None, error_field=None)

    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    address = request.form.get("address", "").strip()
    phone_input = request.form.get("phone", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if first_name == "":
        return render_template(
            "customer_signup.html", error="Enter your first name.", error_field="first_name"
        )
    if len(first_name) > 100:
        return render_template(
            "customer_signup.html", error="First name must be 100 characters or fewer.", error_field="first_name"
        )
    if last_name == "":
        return render_template(
            "customer_signup.html", error="Enter your last name.", error_field="last_name"
        )
    if len(last_name) > 100:
        return render_template(
            "customer_signup.html", error="Last name must be 100 characters or fewer.", error_field="last_name"
        )
    if address == "":
        return render_template(
            "customer_signup.html", error="Enter your address.", error_field="address"
        )
    if len(address) > 200:
        return render_template(
            "customer_signup.html", error="Address must be 200 characters or fewer.", error_field="address"
        )
    if not valid_email(email):
        return render_template(
            "customer_signup.html", error="Enter a valid email address.", error_field="email"
        )
    if len(password) < 8:
        return render_template(
            "customer_signup.html",
            error="Use a password with at least 8 characters.",
            error_field="password",
        )
    if len(password) > 128:
        return render_template(
            "customer_signup.html",
            error="Use a password with 128 characters or fewer.",
            error_field="password",
        )
    if password != confirm_password:
        return render_template(
            "customer_signup.html",
            error="The passwords do not match.",
            error_field="confirm_password",
        )
    if not phone_input:
        return render_template(
            "customer_signup.html",
            error="Enter your phone number.",
            error_field="phone",
        )
    phone = normalize_quebec_phone(phone_input)
    if not valid_phone(phone_input):
        return render_template(
            "customer_signup.html",
            error="Enter a valid 10-digit phone number, such as (514) 555-1234.",
            error_field="phone",
        )
    database = get_db()
    if database.execute("SELECT 1 FROM Users WHERE email = ?", (email,)).fetchone():
        return render_template(
            "customer_signup.html",
            error="An account with this email already exists. Try signing in instead.",
            error_field="email",
        )
    if database.execute("SELECT 1 FROM Customers WHERE email = ?", (email,)).fetchone():
        return render_template(
            "customer_signup.html",
            error="A customer profile with this email already exists. Try signing in instead.",
            error_field="email",
        )
    if phone and database.execute("SELECT 1 FROM Customers WHERE phone = ?", (phone,)).fetchone():
        return render_template(
            "customer_signup.html",
            error="That phone number is already linked to a customer account.",
            error_field="phone",
        )
    password_hash = generate_password_hash(password, method=PASSWORD_HASH_METHOD)
    try:
        stmt = database.execute(
            "INSERT INTO Customers (first_name, last_name, address, phone, email) VALUES (?, ?, ?, ?, ?)",
            (first_name, last_name, address, phone, email))
        customer_id = stmt.lastrowid
        database.execute(
            "INSERT INTO Users (email, password_hash, customer_id) VALUES (?, ?, ?)",
            (email, password_hash, customer_id))
        database.commit()
    except sqlite3.IntegrityError:
        database.rollback()
        return render_template(
            "customer_signup.html",
            error="We couldn't create your account with those details. Please review the form and try again.",
            error_field="email",
        )

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
    app.after_request(expose_csrf)

    checkout_pages = {
        "checkout", "cart.current_cart", "cart.add_item", "cart.update_item",
        "cart.complete_checkout", "cart.scan_tags", "cart.membership", "cart.guest_receipt",
    }
    customer_pages = {
        "account.overview", "account.receipt_history", "account.product_history",
        "account.receipt", "account.email_receipt", "auth.signout",
    }

    @app.before_request
    def require_signin():
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.endpoint != "auth.signup":
            csrf_response = validate_csrf_request()
            if csrf_response is not None:
                return csrf_response
        user_id = session.get("user_id")
        if user_id is not None:
            user = None
            if type(user_id) is int and user_id > 0:
                user = get_db().execute(
                    "SELECT customer_id FROM Users WHERE user_id = ?", (user_id,)
                ).fetchone()
            if user is None or user["customer_id"] != session.get("customer_id"):
                session.clear()
                if request.endpoint == "auth.csrf_token":
                    pass
                elif request.path.startswith("/api/") or request.path == "/alerts":
                    return jsonify({"error": "Please sign in again.", "code": "invalid_session"}), 401
                elif request.endpoint != "auth.signin":
                    return redirect(url_for("auth.signin"))
        if request.endpoint in checkout_pages:
            if session.get("user_id") and session.get("customer_id") is None:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Self-checkout is for guests and customer accounts."}), 403
                return redirect(url_for("fridges"))
            return None
        if request.endpoint in (
            "static", "index", "auth.signin", "auth.signup", "auth.customer_signup",
            "auth.csrf_token",
        ):
            return None
        if not session.get("user_id"):
            if request.path.startswith("/api/") or request.path == "/alerts":
                return jsonify({"error": "Please sign in."}), 401
            return redirect(url_for("auth.signin"))
        if session.get("customer_id") is not None and request.endpoint not in customer_pages:
            if request.path.startswith("/api/") or request.path == "/alerts":
                return jsonify({"error": "Not allowed for customer accounts."}), 403
            return redirect(url_for("account.overview"))
