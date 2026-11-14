import logging
import secrets
import time
from pathlib import Path

from flask import Flask, redirect, session, url_for
from flask_login import LoginManager, current_user
from sqlalchemy import inspect, text

from config import Config, INSTANCE_DIR
from models.database import db
from models.user import User
from routes.auth import auth_bp
from routes.main import main_bp
from routes.transactions import transactions_bp
from routes.budgets import budgets_bp
from routes.goals import goals_bp
from routes.bills import bills_bp
from routes.guardian import guardian_bp
from routes.analytics import analytics_bp
from flask_wtf.csrf import CSRFProtect
from services.security import limiter


csrf = CSRFProtect()
logger = logging.getLogger(__name__)


def _development_secret_key():
    key_path = Path(INSTANCE_DIR) / '.secret_key'
    try:
        key = key_path.read_text(encoding='utf-8').strip()
    except FileNotFoundError:
        key = secrets.token_urlsafe(32)
        try:
            with key_path.open('x', encoding='utf-8') as handle:
                handle.write(key)
        except FileExistsError:
            key = key_path.read_text(encoding='utf-8').strip()
    if not key:
        raise RuntimeError(f'Development secret key file is empty: {key_path}')
    return key


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    Path(INSTANCE_DIR).mkdir(parents=True, exist_ok=True)
    if not app.config.get('SECRET_KEY'):
        if app.config.get('ENVIRONMENT') == 'production':
            raise RuntimeError('SECRET_KEY must be configured in production.')
        app.config['SECRET_KEY'] = _development_secret_key()
    if app.config.get('ENVIRONMENT') == 'production':
        app.config['SESSION_COOKIE_SECURE'] = True
        if len(app.config['SECRET_KEY']) < 32:
            raise RuntimeError('Production SECRET_KEY must contain at least 32 characters.')
        if app.config.get('RATELIMIT_STORAGE_URI', '').startswith('memory://'):
            raise RuntimeError('Configure shared RATELIMIT_STORAGE_URI for production.')
    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        account_id, separator, version = user_id.partition(':')
        if not separator:
            return None
        try:
            user = db.session.get(User, int(account_id))
            if user is None or user.session_version != int(version):
                return None
            return user
        except ValueError:
            return None

    @app.before_request
    def enforce_inactivity_timeout():
        if '_user_id' not in session:
            return None
        if not session.permanent:
            session.permanent = True
        last_activity = session.get('_last_activity')
        now = time.time()
        timeout = app.config['PERMANENT_SESSION_LIFETIME']
        if last_activity is not None and now - last_activity > timeout:
            session.clear()
            return redirect(url_for('auth.login', expired='1'))
        session['_last_activity'] = now
        return None

    @app.route('/')
    def index():
        return redirect(url_for('auth.login'))

    with app.app_context():
        db.create_all()
        user_columns = {column['name'] for column in inspect(db.engine).get_columns('users')}
        if 'session_version' not in user_columns:
            db.session.execute(text(
                'ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0'
            ))
            db.session.commit()

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        response.headers.setdefault('Cross-Origin-Opener-Policy', 'same-origin')
        response.headers.setdefault('X-Permitted-Cross-Domain-Policies', 'none')
        if current_user.is_authenticated:
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        response.headers.setdefault(
            'Content-Security-Policy',
            "default-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "font-src 'self' https://cdnjs.cloudflare.com data:; "
            "img-src 'self' data:; connect-src 'self'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'",
        )
        if app.config['ENVIRONMENT'] == 'production':
            response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
        return response

    @app.errorhandler(500)
    def internal_server_error(error):
        if app.testing:
            raise error
        logger.error(
            'Unhandled application error',
            exc_info=(type(error), error, error.__traceback__),
        )
        return 'An unexpected error occurred. Please try again later.', 500

    @app.errorhandler(429)
    def rate_limit_exceeded(_error):
        return 'Too many attempts. Please wait a while and try again.', 429

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(budgets_bp)
    app.register_blueprint(goals_bp)
    app.register_blueprint(bills_bp)
    app.register_blueprint(guardian_bp)
    app.register_blueprint(analytics_bp)

    return app


app = create_app()


if __name__ == '__main__':
    app.run(debug=app.config['ENVIRONMENT'] == 'development', host='127.0.0.1', port=5000)
