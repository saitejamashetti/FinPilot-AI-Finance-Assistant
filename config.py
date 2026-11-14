import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / 'instance'


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY')
    ENVIRONMENT = os.environ.get('FINPILOT_ENV', 'development').lower()
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', f'sqlite:///{INSTANCE_DIR / "finpilot.db"}')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024
    WTF_CSRF_TIME_LIMIT = 60 * 60
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = (
        os.environ.get('SESSION_COOKIE_SECURE', '').lower() == 'true'
        or os.environ.get('FINPILOT_ENV', 'development').lower() == 'production'
    )
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 12
    SESSION_REFRESH_EACH_REQUEST = True
    RATELIMIT_STORAGE_URI = os.environ.get('RATELIMIT_STORAGE_URI', 'memory://')
    RATELIMIT_HEADERS_ENABLED = True
