import os
import uuid
import zstandard as zstd
from flask import Blueprint, request, jsonify, session, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User
from helpers import sanitize, safe_name, current_user, create_session

compressor = zstd.ZstdCompressor(level=9)
avatar_exts = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/api/login', methods=['POST'])
def login():
    data     = request.get_json(silent=True) or {}
    username = safe_name(data.get('username', ''), 80)
    password = sanitize(data.get('password', ''), 200)
    if not username or not password:
        return jsonify({'error': 'fill in all fields'}), 400
    u = User.query.filter_by(username=username).first()
    if not u or not check_password_hash(u.password, password):
        return jsonify({'error': 'wrong username or password'}), 401
    create_session(u)
    return jsonify({'id': u.id, 'username': u.username, 'role': u.role, 'avatar': u.avatar or ''})


@auth_bp.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'ok': True})


@auth_bp.route('/api/me')
def me():
    u = current_user()
    if not u:
        return jsonify(None)
    return jsonify({'id': u.id, 'username': u.username, 'role': u.role, 'avatar': u.avatar or ''})


@auth_bp.route('/api/me/avatar', methods=['POST'])
def upload_avatar():
    u = current_user()
    if not u:
        return jsonify({'error': 'not logged in'}), 401
    file = request.files.get('avatar')
    if not file or not file.filename:
        return jsonify({'error': 'no file provided'}), 400
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in avatar_exts:
        return jsonify({'error': 'avatars must be an image file'}), 400
    # delete old avatar file if there was one
    if u.avatar:
        old = os.path.join(current_app.config['UPLOAD_FOLDER'], u.avatar)
        if os.path.exists(old):
            os.remove(old)
    name = f"avatar_{u.id}_{uuid.uuid4().hex[:8]}.{ext}.zst"
    dest = os.path.join(current_app.config['UPLOAD_FOLDER'], name)
    with open(dest, 'wb') as f:
        f.write(compressor.compress(file.read()))
    u.avatar = name
    db.session.commit()
    return jsonify({'avatar': name})


@auth_bp.route('/api/me/avatar', methods=['DELETE'])
def delete_avatar():
    u = current_user()
    if not u:
        return jsonify({'error': 'not logged in'}), 401
    if u.avatar:
        path = os.path.join(current_app.config['UPLOAD_FOLDER'], u.avatar)
        if os.path.exists(path):
            os.remove(path)
        u.avatar = ''
        db.session.commit()
    return jsonify({'ok': True})


@auth_bp.route('/api/register', methods=['POST'])
def register():
    data     = request.get_json(silent=True) or {}
    username = sanitize(data.get('username', ''), 80)
    password = data.get('password', '')
    email    = sanitize(data.get('email', ''), 120)
    if not username or len(password) < 6:
        return jsonify({'error': 'username and a password of at least 6 characters required'}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'that username is already taken'}), 400
    db.session.add(User(
        username=username,
        password=generate_password_hash(password),
        recovery_email=email,
        role='user'
    ))
    db.session.commit()
    return jsonify({'ok': True}), 201
