import secrets
import threading
import time
from email.utils import make_msgid

import config
import db
import fan
import mail_service

_sensors = {}
_requests = {}
_stopped = set()


def init_control(app):
    _sensors.clear()
    _requests.clear()
    _stopped.clear()
    app.extensions['select_recipient'] = select_recipient
    if app.config.get('START_SERVICES', True):
        threading.Thread(target=mail_loop, args=(app,), daemon=True).start()


def select_recipient(email):
    db.set_active_recipient(email)
    refresh_requests()


def update_sensor(sensor_id, reading_id, out_of_range):
    if out_of_range:
        _sensors[sensor_id] = reading_id
    else:
        _sensors.pop(sensor_id, None)
        _stopped.discard(sensor_id)
    refresh_requests()


def refresh_requests():
    email = db.get_active_recipient()
    for sensor_id, request in list(_requests.items()):
        if sensor_id not in _sensors or sensor_id in _stopped or request['recipient'] != email:
            del _requests[sensor_id]
    if email and not fan.is_fan_running():
        for sensor_id in _sensors.keys() - _stopped - _requests.keys():
            _requests[sensor_id] = dict(token=secrets.token_hex(12), recipient=email,
                                        message_id=make_msgid(), sent=False, approved=False)


def stop_manually():
    fan.stop_fan()
    _stopped.update(_sensors)
    _requests.clear()


def approve(token):
    refresh_requests()
    for sensor_id, request in _requests.items():
        if request['token'] == token and request['sent'] and not request['approved']:
            if not fan.is_fan_running():
                fan.start_fan()
                db.create_alert(_sensors[sensor_id], 'fan started')
            request['approved'] = True
            return


def process_mail():
    if not config.is_mail_configured():
        return
    refresh_requests()
    requests = [request for request in _requests.values() if not request['approved']]
    sent = [request for request in requests if request['sent']]
    if sent:
        for token in mail_service.find_approvals(sent):
            approve(token)
    for request in requests:
        if not request['sent']:
            try:
                mail_service.send_request(request)
                request['sent'] = True
            except Exception as error:
                print(f'email send failed: {error}')


def mail_loop(app):
    while True:
        try:
            with app.app_context():
                process_mail()
        except Exception as error:
            print(f'email check failed: {error}')
        time.sleep(3)


def get_status():
    refresh_requests()
    return {
        'running': fan.is_fan_running(),
        'pending': sum(not request['approved'] for request in _requests.values()),
        'recipient': db.get_active_recipient(),
        'mail_configured': config.is_mail_configured(),
    }
