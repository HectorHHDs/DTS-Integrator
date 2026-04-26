import re
from flask import Blueprint, request, jsonify
from models import db, Tag
from helpers import safe_name, sanitize, require_admin

tags_bp = Blueprint('tags', __name__)


@tags_bp.route('/api/tags', methods=['GET'])
def list_tags():
    tags = Tag.query.all()
    return jsonify([{'id': t.id, 'name': t.name, 'color': t.color} for t in tags])


@tags_bp.route('/api/tags', methods=['POST'])
def create_tag():
    res = require_admin()
    if isinstance(res, tuple): return res
    data  = request.get_json(silent=True) or {}
    name  = safe_name(data.get('name', ''), 50)
    color = sanitize(data.get('color', '#830494'), 9)
    if not name:
        return jsonify({'error': 'tag name is required'}), 400
    if not re.match(r'^#[0-9a-fA-F]{6}$', color):
        color = '#830494'  # fall back to default if they sent garbage
    if Tag.query.filter_by(name=name).first():
        return jsonify({'error': 'a tag with that name already exists'}), 409
    t = Tag(name=name, color=color)
    db.session.add(t)
    db.session.commit()
    return jsonify({'id': t.id, 'name': t.name, 'color': t.color}), 201


@tags_bp.route('/api/tags/<int:tid>', methods=['DELETE'])
def delete_tag(tid):
    res = require_admin()
    if isinstance(res, tuple): return res
    t = Tag.query.get_or_404(tid)
    db.session.delete(t)
    db.session.commit()
    return jsonify({'ok': True})
