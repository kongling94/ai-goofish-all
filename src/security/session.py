import base64
import hashlib
import hmac
import os
import secrets
import time

COOKIE_NAME = 'all_session'
SESSION_SECONDS = 12 * 3600
_KEY = os.getenv('ALL_SESSION_SECRET', '').encode() or secrets.token_bytes(32)


def issue_session(username):
    payload = base64.urlsafe_b64encode(f'{username}:{int(time.time()) + SESSION_SECONDS}'.encode()).decode()
    signature = hmac.new(_KEY, payload.encode(), hashlib.sha256).hexdigest()
    return f'{payload}.{signature}'


def valid_session(token):
    try:
        payload, signature = token.split('.', 1)
        expected = hmac.new(_KEY, payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return False
        _, expiry = base64.urlsafe_b64decode(payload).decode().rsplit(':', 1)
        return int(expiry) > time.time()
    except (ValueError, AttributeError):
        return False
