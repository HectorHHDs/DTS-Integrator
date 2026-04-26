import os
import importlib
import mimetypes
import traceback
from flask import Flask, send_from_directory, make_response, Response, jsonify
from werkzeug.security import generate_password_hash
import zstandard as zstd

from models import db, User

decompressor = zstd.ZstdDecompressor()

app = Flask(__name__, static_folder='.')
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'neepmeat-trifecta-secret-key-change-in-production')

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(basedir, "db/users.db")}'
app.config['SQLALCHEMY_BINDS'] = {
    'tags':    f'sqlite:///{os.path.join(basedir, "db/tags.db")}',
    'tickets': f'sqlite:///{os.path.join(basedir, "db/tickets.db")}',
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER']      = os.path.join(basedir, 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 512 * 1024 * 1024   # 512mb, discord's own limit is lower anyway

db.init_app(app)

# load each blueprint separately so a broken one doesn't take the whole app down
blueprints = [
    ('routes.auth',    'auth_bp',    'auth'),
    ('routes.users',   'users_bp',   'users'),
    ('routes.tags',    'tags_bp',    'tags'),
    ('routes.tickets', 'tickets_bp', 'tickets'),
]

for module_path, attr, label in blueprints:
    try:
        mod = importlib.import_module(module_path)
        app.register_blueprint(getattr(mod, attr))
        print(f'  loaded: {label}')
    except Exception:
        print(f'  failed to load: {label}')
        traceback.print_exc()


@app.errorhandler(413)
def file_too_large(e):
    return jsonify({'error': 'file is too large'}), 413


@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/css/<path:p>')
def css(p):
    resp = make_response(send_from_directory('css', p))
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.route('/js/<path:p>')
def js(p):
    resp = make_response(send_from_directory('js', p))
    resp.headers['Cache-Control'] = 'no-store'
    return resp


inline_image = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'}
inline_video = {'mp4', 'webm', 'mov', 'avi', 'mkv'}


def serve_upload(filename, disposition):
    # files uploaded through the site are stored compressed as <name>.<ext>.zst
    # discord-downloaded files are stored raw (no .zst) — both paths handled here
    path      = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    is_zst    = filename.endswith('.zst')
    real_name = filename[:-4] if is_zst else filename
    ext       = real_name.rsplit('.', 1)[-1].lower() if '.' in real_name else ''

    if ext in inline_image or ext in inline_video:
        mime = mimetypes.types_map.get(f'.{ext}', 'application/octet-stream')
    else:
        # serve everything else as plain text so nothing can execute in the browser
        mime = 'text/plain; charset=utf-8'

    if is_zst:
        with open(path, 'rb') as f:
            raw = decompressor.decompress(f.read())
        resp = make_response(Response(raw, mimetype=mime))
    else:
        resp = make_response(send_from_directory(app.config['UPLOAD_FOLDER'], filename))
        resp.headers['Content-Type'] = mime

    resp.headers['Content-Disposition']     = disposition
    resp.headers['X-Content-Type-Options']  = 'nosniff'
    resp.headers['Content-Security-Policy'] = (
        "default-src 'none'; img-src 'self' data:; media-src 'self'; style-src 'unsafe-inline'"
    )
    return resp


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return serve_upload(filename, 'inline')


@app.route('/uploads/<filename>/download')
def download_file(filename):
    real_name = filename[:-4] if filename.endswith('.zst') else filename
    return serve_upload(filename, f'attachment; filename="{real_name}"')


if __name__ == '__main__':
    os.makedirs('db', exist_ok=True)
    os.makedirs('uploads', exist_ok=True)
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            db.session.add(User(
                username='admin',
                password=generate_password_hash('admin123'),
                role='administrator'
            ))
            db.session.commit()
            print('default admin created — user: admin, pass: admin123')
    app.run(host='0.0.0.0', port=5050, debug=False)
