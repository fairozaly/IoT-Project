import logging
import smtplib
from datetime import datetime, timezone
from email.utils import make_msgid
from zoneinfo import ZoneInfo

import config
from send_email import send_email

log = logging.getLogger(__name__)

LOCAL_TZ = ZoneInfo("America/Toronto")


def to_local(utc_string):
    """'2026-11-05 22:00:00' (UTC) -> '2026-11-05 17:00' (Montreal)."""
    moment = datetime.strptime(utc_string, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return moment.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")


def assign_receipt_number(db, transaction_id):
    number = f"R{transaction_id:08d}"
    db.execute("UPDATE Transactions SET receipt_number = ? "
               "WHERE transaction_id = ? AND receipt_number IS NULL",
               (number, transaction_id))
    return number


def get_receipt(db, transaction_id):
    txn = db.execute(
        "SELECT t.*, c.first_name, c.last_name, c.email, c.membership_number, c.total_points "
        "FROM Transactions t LEFT JOIN Customers c ON c.customer_id = t.customer_id "
        "WHERE t.transaction_id = ?", (transaction_id,),
    ).fetchone()
    if txn is None:
        return None
    items = db.execute(
        "SELECT p.name, ti.quantity, ti.price_at_sale, "
        "ti.quantity * ti.price_at_sale AS line_total "
        "FROM TransactionItems ti JOIN Products p ON p.product_id = ti.product_id "
        "WHERE ti.transaction_id = ? ORDER BY ti.transaction_item_id", (transaction_id,),
    ).fetchall()
    payments = db.execute(
        "SELECT method, card_type, amount FROM PaymentMethods WHERE transaction_id = ?",
        (transaction_id,),
    ).fetchall()
    return {"transaction": txn, "items": items, "payments": payments}


def build_receipt_text(receipt):
    t = receipt["transaction"]
    lines = ["SMART STORE - RECEIPT", f"Receipt #: {t['receipt_number']}",
             f"Date: {to_local(t['transaction_date'])}", "-" * 40]
    for item in receipt["items"]:
        lines.append(f"{item['name']}  x{item['quantity']}  @ {item['price_at_sale']:.2f}"
                     f"  = {item['line_total']:.2f}")
    lines += ["-" * 40, f"TOTAL: ${t['total_amount']:.2f}", f"Points earned: {t['points_earned']}"]
    if t["membership_number"]:
        lines += [f"Membership #: {t['membership_number']}", f"Points balance: {t['total_points']}"]
    lines.append("Thank you for shopping with us!")
    return "\n".join(lines)


def send_receipt_email(db, transaction_id):
    receipt = get_receipt(db, transaction_id)
    if receipt is None or not receipt["transaction"]["email"]:
        return False  
    t = receipt["transaction"]
    if not config.is_mail_configured():
        log.warning("Mail not configured - receipt %s not emailed.", t["receipt_number"])
        return False
    try:
        send_email(t["email"], f"Your receipt {t['receipt_number']}",
                   build_receipt_text(receipt), make_msgid())
    except (smtplib.SMTPException, OSError):
        log.exception("Could not email receipt %s", t["receipt_number"])
        return False
    with db:
        db.execute("UPDATE Transactions SET receipt_email_sent = 1, "
                   "emailed_at = CURRENT_TIMESTAMP WHERE transaction_id = ?", (transaction_id,))
    return True
