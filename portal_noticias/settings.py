"""
Django settings for portal_noticias project.
Segredos e ambiente vêm de variáveis (.env). Nada confidencial fica hardcoded.
"""
import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env_file(path):
    if not path.exists():
        return
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _env_bool(name, default='false'):
    return os.environ.get(name, default).strip().lower() in ('1', 'true', 'yes', 'on')


def _env_list(name, default=''):
    return [item.strip() for item in os.environ.get(name, default).split(',') if item.strip()]


# Hosts públicos da plataforma (não são tenants). Env pode acrescentar outros.
PLATFORM_HOSTS_PRODUCAO = (
    'portalnoticias.com.br',
    'www.portalnoticias.com.br',
    'meu-site-noticias.onrender.com',
)
ALLOWED_HOSTS_PRODUCAO = (
    'portalnoticias.com.br',
    '.portalnoticias.com.br',
    'www.portalnoticias.com.br',
    'meu-site-noticias.onrender.com',
)
CSRF_TRUSTED_ORIGINS_PRODUCAO = (
    'https://portalnoticias.com.br',
    'https://www.portalnoticias.com.br',
    'https://*.portalnoticias.com.br',
    'https://meu-site-noticias.onrender.com',
)


_load_env_file(BASE_DIR / '.env')

DEBUG = _env_bool('DEBUG', 'true')
PRODUCTION = _env_bool('PRODUCTION', 'false')

SECRET_KEY = os.environ.get('SECRET_KEY', '').strip()
if not SECRET_KEY:
    if DEBUG and not PRODUCTION:
        SECRET_KEY = 'django-insecure-dev-only-change-in-production'
    else:
        raise ImproperlyConfigured('SECRET_KEY é obrigatória quando DEBUG=False ou PRODUCTION=True.')

if os.environ.get('ALLOWED_HOSTS', '').strip():
    ALLOWED_HOSTS = _env_list('ALLOWED_HOSTS')
elif DEBUG and not PRODUCTION:
    ALLOWED_HOSTS = ['*']
elif PRODUCTION:
    ALLOWED_HOSTS = list(ALLOWED_HOSTS_PRODUCAO)
else:
    ALLOWED_HOSTS = ['localhost', '127.0.0.1']

if os.environ.get('CSRF_TRUSTED_ORIGINS', '').strip():
    CSRF_TRUSTED_ORIGINS = _env_list('CSRF_TRUSTED_ORIGINS')
elif PRODUCTION:
    CSRF_TRUSTED_ORIGINS = list(CSRF_TRUSTED_ORIGINS_PRODUCAO)
else:
    CSRF_TRUSTED_ORIGINS = []

EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend',
)
EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587') or 587)
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = _env_bool('EMAIL_USE_TLS', 'true')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@plataforma.local')
RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '').strip()
NOTIFY_EMAILS = _env_list('NOTIFY_EMAILS', '')

FILE_UPLOAD_MAX_MEMORY_SIZE = int(os.environ.get('FILE_UPLOAD_MAX_MEMORY_SIZE', str(52_428_800)))
DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.environ.get('DATA_UPLOAD_MAX_MEMORY_SIZE', str(52_428_800)))

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sitemaps',
    'plataforma.apps.PlataformaConfig',
    'noticias.apps.NoticiasConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'plataforma.middleware.TenantMiddleware',
    'plataforma.middleware.SecurityHeadersMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'portal_noticias.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'noticias.context_processors.site_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'portal_noticias.wsgi.application'

SITE_URL = os.environ.get('SITE_URL', '').rstrip('/')
TENANT_BASE_DOMAIN = os.environ.get('TENANT_BASE_DOMAIN', 'portalnoticias.com.br')
_platform_hosts = [
    h.lower()
    for h in _env_list(
        'PLATFORM_HOSTS',
        'localhost,127.0.0.1,testserver,' + ','.join(PLATFORM_HOSTS_PRODUCAO),
    )
]
for _host in ('localhost', '127.0.0.1', 'testserver', *PLATFORM_HOSTS_PRODUCAO):
    if _host.lower() not in _platform_hosts:
        _platform_hosts.append(_host.lower())
PLATFORM_HOSTS = tuple(_platform_hosts)
# Local: fallback legado ligado por padrão. Produção: desligado, salvo override explícito.
TENANT_COMPAT_FALLBACK = _env_bool(
    'TENANT_COMPAT_FALLBACK',
    'false' if PRODUCTION else 'true',
)

DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            ssl_require=_env_bool('DATABASE_SSL', 'true'),
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'pt-br'
USE_I18N = True
USE_TZ = True
TIME_ZONE = 'America/Porto_Velho'

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
SERVE_MEDIA = DEBUG or _env_bool('SERVE_MEDIA', 'false')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/entrar/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'
PASSWORD_RESET_TIMEOUT = int(os.environ.get('PASSWORD_RESET_TIMEOUT', '3600'))

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = int(os.environ.get('SESSION_COOKIE_AGE', str(60 * 60 * 24 * 14)))

X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'

if PRODUCTION:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = _env_bool('SECURE_HSTS_PRELOAD', 'false')
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Placeholders comerciais (preenchidos nas etapas Kiwify / AdSense por portal)
KIWIFY_WEBHOOK_SECRET = os.environ.get('KIWIFY_WEBHOOK_SECRET', '')
ADSENSE_PLATFORM_CLIENT_ID = os.environ.get('ADSENSE_PLATFORM_CLIENT_ID', '')
DEFAULT_STORAGE = os.environ.get('DEFAULT_FILE_STORAGE', '')
AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID', '')
AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', '')
AWS_STORAGE_BUCKET_NAME = os.environ.get('AWS_STORAGE_BUCKET_NAME', '')

LOGIN_THROTTLE_LIMIT = int(os.environ.get('LOGIN_THROTTLE_LIMIT', '8'))
LOGIN_THROTTLE_WINDOW = int(os.environ.get('LOGIN_THROTTLE_WINDOW', '300'))
SENSITIVE_THROTTLE_LIMIT = int(os.environ.get('SENSITIVE_THROTTLE_LIMIT', '20'))
SENSITIVE_THROTTLE_WINDOW = int(os.environ.get('SENSITIVE_THROTTLE_WINDOW', '600'))
