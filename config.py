import os

from dotenv import load_dotenv

load_dotenv()

MAIL_SENDER_EMAIL = os.getenv("MAIL_SENDER_EMAIL", "")
MAIL_SENDER_SECRET = os.getenv("MAIL_SENDER_SECRET", "")
MAIL_RECIPIENT_EMAIL = os.getenv("MAIL_RECIPIENT_EMAIL", "")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))

IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
IMAP_POLL_INTERVAL = int(os.getenv("IMAP_POLL_INTERVAL", "30"))

APPROVAL_KEYWORD = "yes"


def is_mail_configured():
    return bool(MAIL_SENDER_EMAIL and MAIL_SENDER_SECRET and MAIL_RECIPIENT_EMAIL)
