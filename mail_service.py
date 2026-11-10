import re
from email.utils import parseaddr
from html import unescape

from send_email import send_email
from receive_email import receive_emails


def send_request(request):
    send_email(
        request['recipient'],
        f"sensor threshold exceeded [fan-{request['token']}]",
        'a sensor is above its threshold. reply yes to start the fan. '
        'you can stop it from the dashboard.',
        request['message_id'],
    )

def reply_text(message):
    part = message.get_body(preferencelist=('plain', 'html'))
    if part is None:
        return ''
    content = part.get_content()
    if part.get_content_type() == 'text/html':
        content = re.split(r'<blockquote|<[^>]*class=["\'][^"\']*(?:gmail_quote|yahoo_quoted)',
                           content, maxsplit=1, flags=re.I)[0]
        content = re.sub(r'<[^>]+>', '\n', content)
        content = unescape(content)
    lines = []
    for line in content.splitlines():
        text = line.strip().lower()
        if text.startswith(('>', '--', 'from:', 'sent:', 'subject:', 'to:')):
            break
        if (text.startswith('on ') and 'wrote:' in text) or 'original message' in text:
            break
        lines.append(line)
    return '\n'.join(lines)

def is_approval(message, request):
    if str(message.get('Message-ID', '')) == request['message_id']:
        return False
    sender = parseaddr(message.get('From', ''))[1].casefold()
    if sender != request['recipient'].casefold():
        return False
    references = str(message.get('In-Reply-To', '')) + ' ' + str(message.get('References', ''))
    subject = str(message.get('Subject', '')).lower()
    token = f"[fan-{request['token']}]".lower()
    is_reply = subject.startswith('re:') and token in subject
    if request['message_id'] not in references and not is_reply:
        return False
    words = re.findall(r"\b\w+\b", reply_text(message).lower())
    return 'yes' in words


def find_approvals(requests):
    for request, message in receive_emails(requests):
        if is_approval(message, request):
            yield request['token']
