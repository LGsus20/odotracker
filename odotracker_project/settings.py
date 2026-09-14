import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY')
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

ALLOWED_HOSTS = [host.strip() for host in os.environ.get('ALLOWED_HOSTS', 'localhost').split(',')]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'axes',
    'tracker',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Must be last: wraps the login view to record failures and block locked-out clients.
    'axes.middleware.AxesMiddleware',
]

# AxesStandaloneBackend checks the lockout before delegating to ModelBackend.
AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

ROOT_URLCONF = 'odotracker_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'tracker' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'odotracker_project.wsgi.application'

### In production the db_data/ directory is mounted as a Docker volume so data
### survives container restarts.  In development the DB sits in the project root.
if DEBUG:
    _db_path = BASE_DIR / 'db.sqlite3'
else:
    _db_dir = BASE_DIR / 'db_data'
    _db_dir.mkdir(exist_ok=True)
    _db_path = _db_dir / 'db.sqlite3'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': _db_path,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 14}},
]

# Auth endpoints used by @login_required and the built-in auth views.
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

# django-axes: brute-force lockout, on top of the per-IP limit Caddy enforces.
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_PARAMETERS = [['username']]
AXES_RESET_ON_SUCCESS = True
# W006 nags that 'ip_address' is not in AXES_LOCKOUT_PARAMETERS — intentional:
# locking per username is the whole point (bots usually rotate IPs, not UAs).
SILENCED_SYSTEM_CHECKS = ['axes.W006']

if not DEBUG:
    CSRF_TRUSTED_ORIGINS = [
        origin.strip()
        for origin in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',')
        if origin.strip()
    ]
    if not CSRF_TRUSTED_ORIGINS:
        raise RuntimeError('CSRF_TRUSTED_ORIGINS environment variable is not set')
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30   # 30 Days
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = 'same-origin'
    X_FRAME_OPTIONS = 'DENY'

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'tracker' / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
