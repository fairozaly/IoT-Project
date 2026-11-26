"""Small shared helpers for request validation and browser mutation protection."""

import hmac
import math
import re
import secrets
from urllib.parse import urlsplit

from flask import current_app, jsonify, request, session


EMAIL_RE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")

# Quebec uses the Canadian NANP plan: a 3-digit Quebec area code followed by
# an NXX exchange and a 4-digit line number. Keep this list explicit so a US
# or otherwise non-Quebec number cannot pass a generic 10-digit check.
QUEBEC_AREA_CODES = frozenset(
    {"263", "354", "367", "418", "438", "450", "468", "514", "579", "581", "819", "873"}
)
QUEBEC_PHONE_RE = re.compile(
    r"^(?:(?:\+?1)[\s.-]?)?"
    r"(?:\((?:263|354|367|418|438|450|468|514|579|581|819|873)\)|"
    r"(?:263|354|367|418|438|450|468|514|579|581|819|873))"
    r"[\s.-]?[2-9][0-9]{2}[\s.-]?[0-9]{4}$"
)
CSRF_SESSION_KEY = "_csrf_token"
CSRF_COOKIE_NAME = "csrf_token"


def get_csrf_token():
    token = session.get(CSRF_SESSION_KEY)
    if not isinstance(token, str) or len(token) < 32:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def _origin(value):
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _same_origin_request():
    expected = _origin(request.host_url)
    for header in ("Origin", "Referer"):
        supplied = _origin(request.headers.get(header))
        if supplied is not None:
            return hmac.compare_digest(supplied, expected or "")
    fetch_site = request.headers.get("Sec-Fetch-Site", "").lower()
    return fetch_site in {"same-origin", "same-site"}


def csrf_failure():
    message = "Request could not be verified. Refresh the page and try again."
    if request.path.startswith("/api/") or request.is_json:
        return jsonify(error=message, code="csrf_failed"), 403
    return message, 403


def validate_csrf_request():
    """Return a response when an unsafe request fails CSRF validation.

    The preferred contract is a session token sent as ``X-CSRF-Token`` (or a
    ``csrf_token`` form field). Existing same-origin browser forms and fetches
    are also accepted when the browser supplies a matching Origin/Referer.
    Cross-origin requests are never accepted without the explicit token.
    """
    supplied = request.headers.get("X-CSRF-Token") or request.headers.get("X-CSRFToken")
    if supplied is None and request.form:
        supplied = request.form.get("csrf_token")
    expected = get_csrf_token()
    if supplied is not None:
        if isinstance(supplied, str) and hmac.compare_digest(supplied, expected):
            return None
        return csrf_failure()
    if _same_origin_request():
        return None
    return csrf_failure()


def json_error(message, status=400, code="invalid_input", **details):
    payload = {"error": message, "code": code}
    payload.update(details)
    return jsonify(payload), status


def parse_finite_number(value, field, *, minimum=None, maximum=None):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{field} must be a valid number.")
    if not math.isfinite(number):
        raise ValueError(f"{field} must be a finite number.")
    if minimum is not None and number < minimum:
        raise ValueError(f"{field} must be at least {minimum}.")
    if maximum is not None and number > maximum:
        raise ValueError(f"{field} must be at most {maximum}.")
    return number


def clean_text(value, field, *, required=True, maximum=120):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text.")
    value = value.strip()
    if required and not value:
        raise ValueError(f"{field} is required.")
    if len(value) > maximum:
        raise ValueError(f"{field} must be {maximum} characters or fewer.")
    return value or None


def valid_email(value):
    if not isinstance(value, str):
        return False
    return len(value) <= 254 and bool(EMAIL_RE.fullmatch(value))


def normalize_quebec_phone(value):
    """Return a canonical +1XXXXXXXXXX Quebec number, or None if invalid."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not QUEBEC_PHONE_RE.fullmatch(value):
        return None

    digits = re.sub(r"[^0-9]", "", value)
    if len(digits) == 11:
        if not digits.startswith("1"):
            return None
        digits = digits[1:]
    if len(digits) != 10 or digits[:3] not in QUEBEC_AREA_CODES:
        return None

    # 555-0100 through 555-0199 are reserved fictional numbers.
    if digits[3:6] == "555" and digits[6:8] == "01":
        return None
    return f"+1{digits}"


def valid_phone(value):
    if value is None or value == "":
        return True
    return normalize_quebec_phone(value) is not None


def expose_csrf(response):
    """Expose the token for clients that use the explicit header contract."""
    if request.endpoint == "static":
        return response
    token = get_csrf_token()
    response.headers.setdefault("X-CSRF-Token", token)
    response.set_cookie(
        CSRF_COOKIE_NAME,
        token,
        httponly=False,
        secure=bool(current_app.config.get("SESSION_COOKIE_SECURE", False)),
        samesite="Lax",
    )
    return response
