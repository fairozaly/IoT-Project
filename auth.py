import re
import sqlite3

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db, set_active_recipient


auth = Blueprint("auth", __name__)


def sign_in(user):
    session.clear()
    session["user_id"] = user["user_id"]
    session["email"] = user["email"]
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


@auth.post("/signout")
def signout():
    session.clear()
    return redirect(url_for("auth.signin"))


def init_auth(app):
    app.register_blueprint(auth)
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

    @app.before_request
    def require_signin():
        if request.endpoint in ("static", "auth.signin", "auth.signup"):
            return None
        if not session.get("user_id"):
            if request.path.startswith("/api/") or request.path == "/alerts":
                return jsonify({"error": "Please sign in."}), 401
            return redirect(url_for("auth.signin"))
