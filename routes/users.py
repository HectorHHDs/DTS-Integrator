import secrets
from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash
from models import db, User
from helpers import require_login, require_admin, current_user, safe_name, sanitize

users_bp = Blueprint('users', __name__)


@users_bp.route('/api/users', methods=['GET'])
def list_users():
    me = require_login()
    if isinstance(me, tuple): return me
    users = User.query.all()
    return jsonify([{
        'id':             u.id,
        'username':       u.username,
        'role':           u.role,
        # only admins get to see recovery emails
        'recovery_email': u.recovery_email if me.role == 'administrator' else None,
        'created':        u.created.isoformat()
    } for u in users])


@users_bp.route('/api/users', methods=['POST'])
def create_user():
    res = require_admin()
    if isinstance(res, tuple): return res
    data     = request.get_json(silent=True) or {}
    username = safe_name(data.get('username', ''), 80)
    password = sanitize(data.get('password', ''), 200)
    role     = data.get('role', 'user')
    if role not in ('user', 'contributor', 'administrator'):
        role = 'user'
    if not username or not password:
        return jsonify({'error': 'fill in all fields'}), 400
    if len(password) < 6:
        return jsonify({'error': 'password needs to be at least 6 characters'}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'username already taken'}), 409
    u = User(username=username, password=generate_password_hash(password), role=role)
    db.session.add(u)
    db.session.commit()
    return jsonify({'id': u.id, 'username': u.username, 'role': u.role}), 201


@users_bp.route('/api/users/<int:uid>/role', methods=['PATCH'])
def set_role(uid):
    res = require_admin()
    if isinstance(res, tuple): return res
    data = request.get_json(silent=True) or {}
    role = data.get('role', 'user')
    if role not in ('user', 'contributor', 'administrator'):
        return jsonify({'error': 'not a valid role'}), 400
    u = User.query.get_or_404(uid)
    u.role = role
    db.session.commit()
    return jsonify({'id': u.id, 'username': u.username, 'role': u.role})


@users_bp.route('/api/users/<int:uid>', methods=['DELETE'])
def delete_user(uid):
    res = require_admin()
    if isinstance(res, tuple): return res
    u = User.query.get_or_404(uid)
    db.session.delete(u)
    db.session.commit()
    return jsonify({'ok': True})


@users_bp.route('/api/users/<int:uid>/reset-password', methods=['PATCH'])
def admin_reset_password(uid):
    res = require_admin()
    if isinstance(res, tuple): return res
    data     = request.get_json(silent=True) or {}
    new_pass = data.get('password', '')
    if len(new_pass) < 6:
        return jsonify({'error': 'password too short'}), 400
    u = User.query.get_or_404(uid)
    u.password = generate_password_hash(new_pass)
    db.session.commit()
    return jsonify({'ok': True})


@users_bp.route('/api/users/<int:uid>/invalidate-sessions', methods=['POST'])
def invalidate_sessions(uid):
    res = require_admin()
    if isinstance(res, tuple): return res
    target = User.query.get_or_404(uid)
    # rotating the token means any browser holding the old one gets treated as a guest
    target.session_token = secrets.token_hex(32)
    db.session.commit()
    # special case: if the admin is invalidating themselves, update their own cookie
    # so they don't get kicked out too
    me = current_user()
    if me and me.id == uid:
        from flask import session as flask_session
        flask_session['session_token'] = target.session_token
    return jsonify({'ok': True})
