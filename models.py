from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class User(db.Model):
    id             = db.Column(db.Integer, primary_key=True)
    username       = db.Column(db.String(80), unique=True, nullable=False)
    password       = db.Column(db.String(256), nullable=False)
    recovery_email = db.Column(db.String(120), default='')
    role           = db.Column(db.String(20), default='user')
    created        = db.Column(db.DateTime, default=datetime.utcnow)
    avatar         = db.Column(db.String(200), default='')  # filename in uploads/
    session_token  = db.Column(db.String(64), default='')   # rotate this to kick all active sessions


class Tag(db.Model):
    __bind_key__ = 'tags'
    id    = db.Column(db.Integer, primary_key=True)
    name  = db.Column(db.String(50), unique=True, nullable=False)
    color = db.Column(db.String(9), default='#830494')


class Ticket(db.Model):
    __bind_key__      = 'tickets'
    id                = db.Column(db.Integer, primary_key=True)
    title             = db.Column(db.String(200), nullable=False)
    description       = db.Column(db.Text, nullable=False)
    author            = db.Column(db.String(80), nullable=False)
    tag_ids           = db.Column(db.String(500), default='')   # comma-separated tag IDs
    status            = db.Column(db.String(10), default='open')
    close_msg         = db.Column(db.Text, default='')
    closed_by         = db.Column(db.String(80), default='')
    created           = db.Column(db.DateTime, default=datetime.utcnow)
    updated           = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    attachment        = db.Column(db.String(200), default='')
    discord_thread_id = db.Column(db.BigInteger, default=None, nullable=True)


class Reply(db.Model):
    __bind_key__       = 'tickets'
    id                 = db.Column(db.Integer, primary_key=True)
    ticket_id          = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)
    author             = db.Column(db.String(80), nullable=False)
    content            = db.Column(db.Text, nullable=False)
    created            = db.Column(db.DateTime, default=datetime.utcnow)
    attachment         = db.Column(db.String(200), default='')
    discord_message_id = db.Column(db.BigInteger, default=None, nullable=True, unique=True)
    source             = db.Column(db.String(10), default='web')   # 'web' or 'discord'
    author_role        = db.Column(db.String(20), default='')
    author_avatar      = db.Column(db.String(300), default='')     # discord CDN url or empty


# these three are outgoing queue tables that the bot polls every few seconds.
# flask writes a row, bot picks it up, does the thing, deletes the row.

class OutgoingNewThread(db.Model):
    __bind_key__  = 'tickets'
    id            = db.Column(db.Integer, primary_key=True)
    ticket_id     = db.Column(db.Integer, nullable=False)
    forum_name    = db.Column(db.String(100), nullable=False)
    title         = db.Column(db.String(200), nullable=False)
    description   = db.Column(db.Text, nullable=False)
    author        = db.Column(db.String(80), nullable=False)
    tag_names     = db.Column(db.Text, default='')    # comma-sep, matched to forum's available tags
    attachment    = db.Column(db.String(200), default='')
    created       = db.Column(db.DateTime, default=datetime.utcnow)


class OutgoingAction(db.Model):
    __bind_key__      = 'tickets'
    id                = db.Column(db.Integer, primary_key=True)
    discord_thread_id = db.Column(db.BigInteger, nullable=False)
    action            = db.Column(db.String(10), nullable=False)   # 'lock' or 'unlock'
    message           = db.Column(db.Text, default='')
    web_username      = db.Column(db.String(80), default='')
    web_role          = db.Column(db.String(20), default='')
    created           = db.Column(db.DateTime, default=datetime.utcnow)


class OutgoingReply(db.Model):
    __bind_key__      = 'tickets'
    id                = db.Column(db.Integer, primary_key=True)
    discord_thread_id = db.Column(db.BigInteger, nullable=False)
    web_username      = db.Column(db.String(80), nullable=False)
    web_role          = db.Column(db.String(20), nullable=False)
    content           = db.Column(db.Text, nullable=False)
    attachment        = db.Column(db.String(200), default='')
    created           = db.Column(db.DateTime, default=datetime.utcnow)
