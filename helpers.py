import re
import secrets
from flask import session, jsonify
from models import User

# usernames/tag names can only have these chars — keeps things sane
_safe_re = re.compile(r'^[A-Za-z0-9 _\-!?.@#]+$')


def sanitize(s, maxlen=500):
    return str(s).strip()[:maxlen]


def safe_name(s, maxlen=80):
    s = sanitize(s, maxlen)
    if not _safe_re.match(s):
        return None
    return s


def current_user():
    uid   = session.get('user_id')
    token = session.get('session_token')
    if not uid or not token:
        return None
    u = User.query.get(uid)
    if not u:
        return None
    # if an admin rotated the token, existing sessions just silently stop working
    if u.session_token != token:
        session.clear()
        return None
    return u


def create_session(user):
    # generate a fresh token and store it both on the user row and in the cookie
    token = secrets.token_hex(32)
    user.session_token = token
    from models import db
    db.session.commit()
    session['user_id']       = user.id
    session['session_token'] = token


def require_login():
    u = current_user()
    if not u:
        return jsonify({'error': 'not logged in'}), 401
    return u


def guest_or_user():
    # same as current_user but never returns a 401 — used for read-only endpoints
    return current_user()


def require_admin():
    u = current_user()
    if not u or u.role != 'administrator':
        return jsonify({'error': 'admins only'}), 403
    return u
