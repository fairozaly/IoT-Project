import smtplib
import ssl
from email.mime.text import MIMEText

import config


def send_email(recipient, subject, body, message_id):
    msg = MIMEText(body, _charset='utf-8')
    msg['Subject'] = subject
    msg['From'] = config.MAIL_SENDER_EMAIL
    msg['To'] = recipient
    msg['Message-ID'] = message_id

    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as server:
        server.starttls(context=ssl.create_default_context())
        server.login(config.MAIL_SENDER_EMAIL, config.MAIL_SENDER_SECRET)
        server.sendmail(config.MAIL_SENDER_EMAIL, [recipient], msg.as_string())
