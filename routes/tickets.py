import os
import uuid
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
import zstandard as zstd
from models import db, Ticket, Reply, Tag, OutgoingReply, OutgoingAction, OutgoingNewThread
from helpers import sanitize, require_login, guest_or_user

compressor = zstd.ZstdCompressor(level=9)
log = logging.getLogger(__name__)

tickets_bp = Blueprint('tickets', __name__)

# only regular users are restricted to images/videos.
# contributors and admins can attach whatever they want.
user_allowed_exts = {
    'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg',
    'mp4', 'webm', 'mov', 'mkv', 'avi',
}


def save_upload(file):
    if not file or not file.filename:
        return ''
    ext  = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'bin'
    name = f"{uuid.uuid4().hex}.{ext}.zst"
    dest = os.path.join(current_app.config['UPLOAD_FOLDER'], name)
    with open(dest, 'wb') as f:
        f.write(compressor.compress(file.read()))
    return name


def check_user_attachment(file, role):
    if role != 'user':
        return None
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in user_allowed_exts:
        return 'regular users can only attach images or videos'
    return None


def tag_lookup():
    return {t.id: {'id': t.id, 'name': t.name, 'color': t.color} for t in Tag.query.all()}


def tag_list(ids_str, lookup):
    if not ids_str:
        return []
    return [lookup[int(i)] for i in ids_str.split(',') if i and int(i) in lookup]


def queue_discord_reply(ticket_id, username, role, content, attachment):
    try:
        ticket = Ticket.query.get(ticket_id)
        if not ticket or not ticket.discord_thread_id:
            return
        db.session.add(OutgoingReply(
            discord_thread_id=ticket.discord_thread_id,
            web_username=username,
            web_role=role,
            content=content,
            attachment=attachment,
        ))
        db.session.commit()
    except Exception as e:
        log.warning('could not queue discord reply: %s', e)


def queue_discord_action(ticket_id, action, message, username, role):
    try:
        ticket = Ticket.query.get(ticket_id)
        if not ticket or not ticket.discord_thread_id:
            return
        db.session.add(OutgoingAction(
            discord_thread_id=ticket.discord_thread_id,
            action=action,
            message=message,
            web_username=username,
            web_role=role,
        ))
        db.session.commit()
    except Exception as e:
        log.warning('could not queue discord action: %s', e)


def queue_new_thread(ticket_id, forum_name, title, description, author, tag_names, attachment):
    try:
        db.session.add(OutgoingNewThread(
            ticket_id=ticket_id,
            forum_name=forum_name,
            title=title,
            description=description,
            author=author,
            tag_names=','.join(tag_names),
            attachment=attachment,
        ))
        db.session.commit()
    except Exception as e:
        log.warning('could not queue new thread: %s', e)


@tickets_bp.route('/api/tickets', methods=['GET'])
def list_tickets():
    # guests can browse, they just can't do anything
    guest_or_user()

    status  = request.args.get('status')
    tag_ids = request.args.getlist('tag')   # supports ?tag=1&tag=2 for multi-tag filtering
    author  = request.args.get('author')
    sort    = request.args.get('sort', 'newest')

    q = Ticket.query
    if status and status != 'all':
        q = q.filter_by(status=status)
    if author:
        q = q.filter_by(author=author)
    for tid in tag_ids:
        if tid:
            q = q.filter(Ticket.tag_ids.contains(str(tid)))
    q = q.order_by(Ticket.created.asc() if sort == 'oldest' else Ticket.created.desc())

    lookup = tag_lookup()
    return jsonify([{
        'id':          t.id,
        'title':       t.title,
        'description': t.description,
        'author':      t.author,
        'tags':        tag_list(t.tag_ids, lookup),
        'status':      t.status,
        'close_msg':   t.close_msg,
        'closed_by':   t.closed_by,
        'created':     t.created.isoformat(),
        'updated':     t.updated.isoformat(),
        'attachment':  t.attachment,
    } for t in q.all()])


@tickets_bp.route('/api/tickets', methods=['POST'])
def create_ticket():
    u = require_login()
    if isinstance(u, tuple): return u
    title       = sanitize(request.form.get('title', ''), 200)
    description = sanitize(request.form.get('description', ''), 4000)
    tag_ids_raw = request.form.get('tag_ids', '').split(',')
    if not title or not description:
        return jsonify({'error': 'title and description are both required'}), 400
    file = request.files.get('file')
    err  = check_user_attachment(file, u.role)
    if err:
        return jsonify({'error': err}), 400
    safe_ids   = ','.join(str(int(i)) for i in tag_ids_raw if str(i).strip().isdigit())
    attachment = save_upload(file)
    t = Ticket(title=title, description=description, author=u.username,
               tag_ids=safe_ids, attachment=attachment)
    db.session.add(t)
    db.session.commit()

    # figure out which forum channel this should go to.
    # if it has the suggestion tag, send it to #suggestions. otherwise bugs.
    names = [tag.name for tag in Tag.query.filter(
        Tag.id.in_([int(i) for i in safe_ids.split(',') if i])
    ).all()] if safe_ids else []
    suggestion_tag = Tag.query.filter(Tag.name.ilike('suggestion%')).first()
    has_suggestion = suggestion_tag and str(suggestion_tag.id) in safe_ids.split(',')
    forum = 'suggestions' if has_suggestion else 'modpack-crashes-and-bugs'
    queue_new_thread(t.id, forum, title, description, u.username, names, attachment)

    return jsonify({'id': t.id}), 201


@tickets_bp.route('/api/tickets/<int:tid>/close', methods=['PATCH'])
def close_ticket(tid):
    u = require_login()
    if isinstance(u, tuple): return u
    t = Ticket.query.get_or_404(tid)
    if t.status == 'closed':
        return jsonify({'error': 'already closed'}), 400
    data      = request.get_json(silent=True) or {}
    close_msg = sanitize(data.get('message', ''), 1000)
    if not (u.role in ('administrator', 'contributor') or t.author == u.username):
        return jsonify({'error': 'you don\'t have permission to close this ticket'}), 403
    t.status    = 'closed'
    t.close_msg = close_msg
    t.closed_by = u.username
    t.updated   = datetime.utcnow()
    db.session.commit()
    queue_discord_action(t.id, 'lock', close_msg, u.username, u.role)
    return jsonify({'ok': True})


@tickets_bp.route('/api/tickets/<int:tid>/reopen', methods=['PATCH'])
def reopen_ticket(tid):
    u = require_login()
    if isinstance(u, tuple): return u
    t = Ticket.query.get_or_404(tid)
    if t.status == 'open':
        return jsonify({'error': 'already open'}), 400
    if not (u.role in ('administrator', 'contributor') or t.author == u.username):
        return jsonify({'error': 'you don\'t have permission to reopen this ticket'}), 403
    t.status    = 'open'
    t.close_msg = ''
    t.closed_by = ''
    t.updated   = datetime.utcnow()
    db.session.commit()
    queue_discord_action(t.id, 'unlock', '', u.username, u.role)
    return jsonify({'ok': True})


@tickets_bp.route('/api/tickets/<int:tid>/replies', methods=['GET'])
def get_replies(tid):
    u        = guest_or_user()
    is_guest = u is None
    replies  = Reply.query.filter_by(ticket_id=tid).order_by(Reply.created.asc()).all()

    # grab avatars for web users so the frontend can show them
    from models import User as UserModel
    web_avatars = {}
    for r in replies:
        if (r.source or 'web') == 'web' and r.author not in web_avatars:
            wu = UserModel.query.filter_by(username=r.author).first()
            web_avatars[r.author] = wu.avatar if wu and wu.avatar else ''

    return jsonify([{
        'id':            r.id,
        'author':        r.author,
        'content':       r.content,
        'created':       r.created.isoformat(),
        'attachment':    '' if is_guest else r.attachment,   # guests don't get attachments
        'source':        r.source or 'web',
        'author_role':   r.author_role or '',
        'author_avatar': r.author_avatar if (r.source or 'web') == 'discord'
                         else web_avatars.get(r.author, ''),
    } for r in replies])


@tickets_bp.route('/api/tickets/<int:tid>/replies', methods=['POST'])
def post_reply(tid):
    u = require_login()
    if isinstance(u, tuple): return u
    t       = Ticket.query.get_or_404(tid)
    content = sanitize(request.form.get('content', ''), 2000)
    if not content:
        return jsonify({'error': 'reply can\'t be empty'}), 400
    file = request.files.get('file')
    err  = check_user_attachment(file, u.role)
    if err:
        return jsonify({'error': err}), 400
    attachment = save_upload(file)
    r = Reply(ticket_id=t.id, author=u.username, content=content,
              attachment=attachment, source='web', author_role=u.role)
    db.session.add(r)
    db.session.commit()
    queue_discord_reply(t.id, u.username, u.role, content, attachment)
    return jsonify({'id': r.id, 'author': r.author, 'content': r.content}), 201
