import email
import imaplib
from email import policy

import config


def receive_emails(requests):
    with imaplib.IMAP4_SSL(config.IMAP_HOST, config.IMAP_PORT, timeout=15) as mailbox:
        mailbox.login(config.MAIL_SENDER_EMAIL, config.MAIL_SENDER_SECRET)
        mailbox.select('INBOX', readonly=True)
        for request in requests:
            status, data = mailbox.uid('search', None, 'OR', 'HEADER', 'SUBJECT',
                                       f'"fan-{request["token"]}"',
                                       'HEADER', 'IN-REPLY-TO',
                                       f'"{request["message_id"]}"')
            if status != 'OK':
                continue
            for uid in data[0].split():
                status, msg_data = mailbox.uid('fetch', uid, '(BODY.PEEK[])')
                if status != 'OK':
                    continue
                for part in msg_data:
                    if isinstance(part, tuple):
                        yield request, email.message_from_bytes(part[1], policy=policy.default)
