# discord bridge for neepmeat trifecta
# runs as a separate process from app.py — start both in separate terminals
#
# pip install discord.py aiohttp zstandard
#
# needs these intents enabled in the discord developer portal:
#   - server members intent
#   - message content intent

import asyncio
import io
import logging
import os
import re
import sys
import uuid
from datetime import datetime

import aiohttp
import discord
import zstandard as zstd
from discord.ext import commands, tasks

# we need flask's app context to use sqlalchemy outside of a request
sys.path.insert(0, os.path.dirname(__file__))
from flask import Flask as _Flask
from models import db, Tag, Ticket, Reply, OutgoingReply, OutgoingAction, OutgoingNewThread

flask_app = _Flask(__name__)
basedir   = os.path.abspath(os.path.dirname(__file__))
flask_app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(basedir, "db/users.db")}'
flask_app.config['SQLALCHEMY_BINDS'] = {
    'tags':    f'sqlite:///{os.path.join(basedir, "db/tags.db")}',
    'tickets': f'sqlite:///{os.path.join(basedir, "db/tickets.db")}',
}
flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(flask_app)
with flask_app.app_context():
    db.create_all()

compressor   = zstd.ZstdCompressor(level=9)
decompressor = zstd.ZstdDecompressor()

# settings
bot_token          = os.environ.get('DISCORD_BOT_TOKEN', 'YOUR_TOKEN_HERE')
watched_forums     = {'suggestions', 'modpack-crashes-and-bugs'}
suggestion_tag     = 'Suggestion'
suggestion_color   = '#0057d8'
closed_tag_names   = {'closed', 'resolved', 'fixed', 'done', 'wontfix', "won't fix"}
default_tag_color  = '#830494'
upload_dir         = os.path.join(basedir, 'uploads')
poll_interval      = 3   # seconds between queue polls

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
log = logging.getLogger('trifecta-bot')

intents = discord.Intents.default()
intents.message_content = True
intents.members         = True
intents.guilds          = True

bot = commands.Bot(command_prefix='!', intents=intents)

# maps discord thread id → db ticket id, rebuilt from db on startup
thread_to_ticket: dict[int, int] = {}


# --- name / avatar helpers ---

async def resolve_display_name(guild, user):
    if user is None:
        return 'unknown'
    if isinstance(user, discord.Member):
        return user.display_name
    member = guild.get_member(user.id)
    if member is None:
        try:
            member = await guild.fetch_member(user.id)
        except (discord.NotFound, discord.HTTPException):
            pass
    if member is not None:
        return member.display_name
    return getattr(user, 'display_name', None) or getattr(user, 'name', None) or 'unknown'


def name_from_message(message):
    author = message.author
    if isinstance(author, discord.Member):
        return author.display_name
    return getattr(author, 'display_name', None) or getattr(author, 'name', None) or 'unknown'


def avatar_url_from(user):
    if user is None:
        return ''
    try:
        av = user.display_avatar if hasattr(user, 'display_avatar') else user.avatar
        if av:
            return str(av.url)
    except Exception:
        pass
    return ''


# --- attachment helpers ---

def discord_file_from_stored(stored_name):
    # decompresses .zst files in memory before sending to discord
    # so discord sees the original bytes with the right filename
    path = os.path.join(upload_dir, stored_name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'rb') as f:
            raw = f.read()
        if stored_name.endswith('.zst'):
            raw       = decompressor.decompress(raw)
            real_name = stored_name[:-4]
        else:
            real_name = stored_name
        return discord.File(io.BytesIO(raw), filename=real_name)
    except Exception as e:
        log.error('could not read upload %s for discord: %s', stored_name, e)
        return None


async def download_attachment(attachment):
    os.makedirs(upload_dir, exist_ok=True)

    # use the discord snowflake id as the filename so the same file is never downloaded twice
    ext  = attachment.filename.rsplit('.', 1)[-1].lower() if '.' in attachment.filename else 'bin'
    name = f"discord_{attachment.id}.{ext}.zst"
    dest = os.path.join(upload_dir, name)

    if os.path.exists(dest):
        return name

    # migrate any old uncompressed version left over from before compression was added
    legacy = os.path.join(upload_dir, f"discord_{attachment.id}.{ext}")
    if os.path.exists(legacy):
        with open(legacy, 'rb') as f:
            raw = f.read()
        with open(dest, 'wb') as f:
            f.write(compressor.compress(raw))
        os.remove(legacy)
        log.info('compressed legacy file discord_%s.%s', attachment.id, ext)
        return name

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(attachment.url) as resp:
                if resp.status != 200:
                    log.warning('could not download %s: http %d', attachment.filename, resp.status)
                    return ''
                raw = await resp.read()
        with open(dest, 'wb') as f:
            f.write(compressor.compress(raw))
        log.info('saved attachment: %s → %s', attachment.filename, name)
        return name
    except Exception as e:
        log.error('attachment download failed: %s', e)
        return ''


async def download_first_attachment(message):
    if message is None or not message.attachments:
        return ''
    return await download_attachment(message.attachments[0])


# --- tag helpers ---

def get_or_create_tag(name, color):
    existing = Tag.query.filter_by(name=name).first()
    if existing:
        return existing.id
    tag = Tag(name=name, color=color)
    db.session.add(tag)
    db.session.flush()
    return tag.id


def discord_color_to_hex(color):
    if color is None:
        return default_tag_color
    try:
        return f'#{color.value:06x}'
    except Exception:
        return default_tag_color


def sync_forum_tags(forum, is_suggestions):
    mapping = {}
    for ft in forum.available_tags:
        color      = discord_color_to_hex(getattr(ft, 'colour', None))
        mapping[ft.id] = get_or_create_tag(ft.name, color)
    if is_suggestions:
        get_or_create_tag(suggestion_tag, suggestion_color)
    db.session.commit()
    return mapping


def build_tag_ids_str(applied_tags, mapping, extra_ids):
    ids = [str(mapping[t.id]) for t in applied_tags if t.id in mapping]
    for eid in extra_ids:
        s = str(eid)
        if s not in ids:
            ids.append(s)
    return ','.join(ids)


def thread_is_closed(thread):
    if thread.locked or thread.archived:
        return True
    for tag in thread.applied_tags:
        if tag.name.lower() in closed_tag_names:
            return True
    return False


def rebuild_thread_cache():
    with flask_app.app_context():
        rows = Ticket.query.filter(Ticket.discord_thread_id.isnot(None)).all()
        for t in rows:
            thread_to_ticket[t.discord_thread_id] = t.id
    log.info('rebuilt cache: %d discord-linked tickets', len(thread_to_ticket))


async def get_first_message(thread):
    try:
        return await thread.fetch_message(thread.id)
    except discord.NotFound:
        async for msg in thread.history(limit=1, oldest_first=True):
            return msg
    return None


# --- thread / reply sync ---

async def sync_thread(thread, tag_mapping, is_suggestions):
    status = 'closed' if thread_is_closed(thread) else 'open'

    extra_ids = []
    if is_suggestions:
        with flask_app.app_context():
            stag = Tag.query.filter_by(name=suggestion_tag).first()
            if stag:
                extra_ids = [stag.id]

    tag_ids_str = build_tag_ids_str(thread.applied_tags, tag_mapping, extra_ids)

    with flask_app.app_context():
        existing = Ticket.query.filter_by(discord_thread_id=thread.id).first()
        if existing:
            # already in db — just update status and tags, no api calls needed
            existing.status  = status
            existing.tag_ids = tag_ids_str
            db.session.commit()
            thread_to_ticket[thread.id] = existing.id
            return existing.id

    # new thread — need to fetch the opening message, resolve the author name, etc
    opening    = await get_first_message(thread)
    desc       = opening.content if opening else '(no description)'
    created_at = thread.created_at or datetime.utcnow()
    author     = await resolve_display_name(thread.guild, thread.owner)

    with flask_app.app_context():
        # fallback lookup for tickets that were imported before discord_thread_id existed
        existing = Ticket.query.filter_by(title=thread.name, author=author).first()
        if existing:
            existing.status            = status
            existing.tag_ids           = tag_ids_str
            existing.discord_thread_id = thread.id
            if not existing.attachment and opening:
                existing.attachment = await download_first_attachment(opening)
            db.session.commit()
            thread_to_ticket[thread.id] = existing.id
            return existing.id

    attachment = await download_first_attachment(opening)

    with flask_app.app_context():
        t = Ticket(
            title=thread.name, description=desc, author=author,
            tag_ids=tag_ids_str, status=status, attachment=attachment,
            discord_thread_id=thread.id, created=created_at, updated=created_at,
        )
        db.session.add(t)
        db.session.commit()
        thread_to_ticket[thread.id] = t.id
        log.info('  new ticket #%d: %s [%s]', t.id, t.title, status)
        return t.id


# regex to detect messages the bot itself posted as web-reply bridges
# format: **[username]** *(via website · Role)*
web_reply_re = re.compile(r'^[*][*]\[(.+?)\][*][*] [*]\(via website · (\w+)\)[*]\n', re.DOTALL)


def parse_bot_bridge_message(content):
    # i have no idea about this part, i forgot after i had a brain blast and added this feature
    m = web_reply_re.match(content)
    if not m:
        return None
    return m.group(1), content[m.end():]


async def sync_replies(thread, ticket_id, since_id=None):
    to_insert   = []
    to_backfill = []  # (reply_id, attachment) for old rows that are missing their attachment
    first       = True

    history_kwargs = {'limit': None, 'oldest_first': True}
    if since_id:
        history_kwargs['after']       = discord.Object(id=since_id)
        history_kwargs['oldest_first'] = True

    async for msg in thread.history(**history_kwargs):
        if first:
            first = False
            continue

        if msg.author.bot:
            parsed = parse_bot_bridge_message(msg.content)
            if parsed is None:
                continue   # some unrelated bot message, skip it
            author, body = parsed
        else:
            author = name_from_message(msg)
            body   = msg.content[:2000]

        with flask_app.app_context():
            existing = Reply.query.filter_by(discord_message_id=msg.id).first()
            if existing:
                if not existing.attachment and msg.attachments:
                    att = await download_first_attachment(msg)
                    if att:
                        to_backfill.append((existing.id, att))
                continue

        att    = await download_first_attachment(msg)
        avatar = avatar_url_from(msg.author)
        to_insert.append((msg.id, author, body[:2000], msg.created_at, att, avatar))

    if not to_insert and not to_backfill:
        return

    with flask_app.app_context():
        for msg_id, author, content, created, att, avatar in to_insert:
            db.session.add(Reply(
                ticket_id=ticket_id, author=author, content=content,
                created=created, attachment=att, discord_message_id=msg_id,
                source='discord', author_role='', author_avatar=avatar,
            ))
        for reply_id, att in to_backfill:
            r = Reply.query.get(reply_id)
            if r:
                r.attachment = att
        db.session.commit()


async def sync_forum(forum):
    is_suggestions = forum.name.lower() == 'suggestions'
    log.info('syncing #%s', forum.name)

    with flask_app.app_context():
        tag_mapping = sync_forum_tags(forum, is_suggestions)
        known_ids   = {
            t.discord_thread_id
            for t in Ticket.query.filter(Ticket.discord_thread_id.isnot(None)).all()
        }

    threads = list(forum.threads)
    try:
        async for t in forum.archived_threads(limit=None):
            threads.append(t)
    except Exception as e:
        log.warning('could not fetch archived threads for #%s: %s', forum.name, e)

    new_count = sum(1 for t in threads if t.id not in known_ids)
    log.info('  %d threads (%d known, %d new)', len(threads), len(threads) - new_count, new_count)

    for thread in threads:
        try:
            ticket_id = await sync_thread(thread, tag_mapping, is_suggestions)
            if not ticket_id:
                continue
            if thread.id in known_ids:
                # only fetch replies we haven't seen yet
                with flask_app.app_context():
                    latest = (
                        Reply.query.filter_by(ticket_id=ticket_id)
                        .filter(Reply.discord_message_id.isnot(None))
                        .order_by(Reply.discord_message_id.desc())
                        .first()
                    )
                since = latest.discord_message_id if latest else None
                await sync_replies(thread, ticket_id, since_id=since)
            else:
                await sync_replies(thread, ticket_id)
        except Exception as e:
            log.error('failed to sync "%s": %s', thread.name, e)

    log.info('  done with #%s', forum.name)


# --- outgoing queue pollers ---

@tasks.loop(seconds=poll_interval)
async def poll_replies():
    with flask_app.app_context():
        pending = OutgoingReply.query.order_by(OutgoingReply.id).all()
        if not pending:
            return
        for row in pending:
            thread = bot.get_channel(row.discord_thread_id)
            if thread is None:
                try:
                    thread = await bot.fetch_channel(row.discord_thread_id)
                except Exception as e:
                    log.error('could not find thread %d: %s', row.discord_thread_id, e)
                    continue
            role  = row.web_role.capitalize()
            msg   = f'**[{row.web_username}]** *(via website · {role})*\n{row.content}'
            dfile = discord_file_from_stored(row.attachment) if row.attachment else None
            try:
                await thread.send(msg, file=dfile) if dfile else await thread.send(msg)
                db.session.delete(row)
                db.session.commit()
                log.info('sent reply from %s to thread %d', row.web_username, row.discord_thread_id)
            except Exception as e:
                log.error('failed to send reply row %d: %s', row.id, e)


@tasks.loop(seconds=poll_interval)
async def poll_actions():
    # handles lock/unlock of threads when a ticket is closed or reopened from the site
    with flask_app.app_context():
        pending = OutgoingAction.query.order_by(OutgoingAction.id).all()
        if not pending:
            return
        for row in pending:
            thread = bot.get_channel(row.discord_thread_id)
            if thread is None:
                try:
                    thread = await bot.fetch_channel(row.discord_thread_id)
                except Exception as e:
                    log.error('could not find thread %d: %s', row.discord_thread_id, e)
                    continue

            role = row.web_role.capitalize() if row.web_role else 'user'
            try:
                if row.action == 'lock':
                    if row.message and row.message.strip():
                        await thread.send(f'**[{row.web_username}]** *(closed via website · {role})*\n' + row.message)
                    elif row.web_username:
                        await thread.send(f'**[{row.web_username}]** *(closed via website · {role})*')
                elif row.action == 'unlock':
                    if row.web_username:
                        await thread.send(f'**[{row.web_username}]** *(reopened via website · {role})*')
                db.session.delete(row)
                db.session.commit()
            except Exception as e:
                log.error('failed sending action message for row %d: %s', row.id, e)
                continue

            # locking requires manage threads permission — if we don't have it, just log and move on
            try:
                if row.action == 'lock':
                    await thread.edit(locked=True, archived=True)
                elif row.action == 'unlock':
                    await thread.edit(locked=False, archived=False)
            except discord.Forbidden:
                log.warning('no permission to %s thread %d — grant the bot manage threads', row.action, row.discord_thread_id)
            except Exception as e:
                log.error('thread edit failed for %d: %s', row.discord_thread_id, e)


@tasks.loop(seconds=poll_interval)
async def poll_new_threads():
    # when someone submits a ticket from the site, we create a matching discord forum post here
    with flask_app.app_context():
        pending = OutgoingNewThread.query.order_by(OutgoingNewThread.id).all()
        if not pending:
            return
        for row in pending:
            forum = None
            for guild in bot.guilds:
                for ch in guild.channels:
                    if isinstance(ch, discord.ForumChannel) and ch.name.lower() == row.forum_name.lower():
                        forum = ch
                        break
                if forum:
                    break

            if forum is None:
                log.error('could not find forum channel "%s"', row.forum_name)
                continue

            applied = []
            if row.tag_names:
                wanted = {n.strip().lower() for n in row.tag_names.split(',') if n.strip()}
                applied = [ft for ft in forum.available_tags if ft.name.lower() in wanted]

            body  = f'{row.description}\n\n*— submitted by **{row.author}** via website*'
            dfile = discord_file_from_stored(row.attachment) if row.attachment else None

            try:
                kwargs = {'name': row.title, 'content': body}
                if applied:
                    kwargs['applied_tags'] = applied
                if dfile:
                    kwargs['file'] = dfile

                new_thread, _ = await forum.create_thread(**kwargs)

                with flask_app.app_context():
                    t = Ticket.query.get(row.ticket_id)
                    if t:
                        t.discord_thread_id = new_thread.id
                        db.session.commit()
                thread_to_ticket[new_thread.id] = row.ticket_id
                log.info('created discord thread "%s" for ticket #%d', row.title, row.ticket_id)
                db.session.delete(row)
                db.session.commit()
            except Exception as e:
                log.error('failed to create thread for row %d: %s', row.id, e)


# --- bot events ---

@bot.event
async def on_ready():
    log.info('logged in as %s', bot.user)
    rebuild_thread_cache()
    for guild in bot.guilds:
        for channel in guild.channels:
            if isinstance(channel, discord.ForumChannel) and channel.name.lower() in watched_forums:
                try:
                    await sync_forum(channel)
                except Exception as e:
                    log.error('error syncing #%s: %s', channel.name, e)
    poll_replies.start()
    poll_actions.start()
    poll_new_threads.start()
    log.info('ready. polling every %ds', poll_interval)


@bot.event
async def on_thread_create(thread):
    if not isinstance(thread.parent, discord.ForumChannel):
        return
    if thread.parent.name.lower() not in watched_forums:
        return
    log.info('new thread: "%s" in #%s', thread.name, thread.parent.name)
    await asyncio.sleep(1)   # give discord a moment to attach the opening message
    is_suggestions = thread.parent.name.lower() == 'suggestions'
    with flask_app.app_context():
        tag_mapping = sync_forum_tags(thread.parent, is_suggestions)
    ticket_id = await sync_thread(thread, tag_mapping, is_suggestions)
    if ticket_id:
        await sync_replies(thread, ticket_id)


@bot.event
async def on_message(message):
    if message.author.bot:
        await bot.process_commands(message)
        return

    thread = message.channel
    if not isinstance(thread, discord.Thread):
        await bot.process_commands(message)
        return
    if not isinstance(thread.parent, discord.ForumChannel):
        await bot.process_commands(message)
        return
    if thread.parent.name.lower() not in watched_forums:
        await bot.process_commands(message)
        return
    if message.id == thread.id:   # this is the opening post, already handled by on_thread_create
        await bot.process_commands(message)
        return

    ticket_id = thread_to_ticket.get(thread.id)
    if ticket_id is None:
        is_suggestions = thread.parent.name.lower() == 'suggestions'
        with flask_app.app_context():
            tag_mapping = sync_forum_tags(thread.parent, is_suggestions)
        ticket_id = await sync_thread(thread, tag_mapping, is_suggestions)

    if ticket_id is None:
        await bot.process_commands(message)
        return

    author = name_from_message(message)
    att    = await download_first_attachment(message)
    avatar = avatar_url_from(message.author)

    with flask_app.app_context():
        if Reply.query.filter_by(discord_message_id=message.id).first():
            await bot.process_commands(message)
            return
        db.session.add(Reply(
            ticket_id=ticket_id, author=author, content=message.content[:2000],
            created=message.created_at, attachment=att, discord_message_id=message.id,
            source='discord', author_role='', author_avatar=avatar,
        ))
        db.session.commit()
        log.info('reply from %s on ticket #%d', author, ticket_id)

    await bot.process_commands(message)


@bot.event
async def on_thread_update(before, after):
    if not isinstance(after.parent, discord.ForumChannel):
        return
    if after.parent.name.lower() not in watched_forums:
        return

    ticket_id = thread_to_ticket.get(after.id)
    if ticket_id is None:
        return

    lock_changed    = before.locked   != after.locked
    archive_changed = before.archived != after.archived
    tags_changed    = {t.id for t in before.applied_tags} != {t.id for t in after.applied_tags}

    if not (lock_changed or archive_changed or tags_changed):
        return

    new_status = 'closed' if thread_is_closed(after) else 'open'

    with flask_app.app_context():
        t = Ticket.query.get(ticket_id)
        if t and t.status != new_status:
            t.status  = new_status
            t.updated = datetime.utcnow()
            if new_status == 'open':
                t.close_msg = ''
                t.closed_by = ''
            db.session.commit()
            log.info('ticket #%d is now %s', ticket_id, new_status)


if __name__ == '__main__':
    token = os.environ.get('DISCORD_BOT_TOKEN', bot_token)
    if not token or token == 'YOUR_TOKEN_HERE':
        sys.exit('set the DISCORD_BOT_TOKEN env variable before running')
    bot.run(token)
