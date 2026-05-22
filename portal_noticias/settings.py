"""
Django settings for portal_noticias project.
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-800m9*oh3qe6gaie!l4+2tf34w+=ha1a!_xtif!hr9m2(9xtom'
DEBUG = True
ALLOWED_HOSTS = ['*']

# Identidade do portal — Jiparaná, Rondônia
SITE_NAME = 'Notícias Ji-Paraná'
SITE_NAME_SHORT = 'Ji-Paraná'
SITE_CITY = 'Jiparaná'
SITE_STATE = 'Rondônia'
SITE_REGION = 'Ji-Paraná e região'
SITE_SLOGAN = 'Notícias em tempo real'
SITE_TAGLINE = 'Notícias Ji-Paraná e região — em tempo real'
SITE_DESCRIPTION = (
    'Notícias Ji-Paraná e região em tempo real. Informação local, lojas e comunidade '
    'com conteúdo revisado antes de publicar.'
)
SITE_LOGO = 'img/logo.png'
SITE_FAVICON = 'img/favicon.png'
SITE_LAT = -10.8854
SITE_LON = -61.9516

# E-mail: notificações de curtida, comentário e novos envios
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'noreply@noticias-jiparana.local'
# Coloque seu e-mail aqui para receber alertas (também envia para usuários staff do admin)
NOTIFY_EMAILS = []

FILE_UPLOAD_MAX_MEMORY_SIZE = 52428800
DATA_UPLOAD_MAX_MEMORY_SIZE = 52428800

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'noticias.apps.NoticiasConfig',
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




import dj_database_url
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASES = {
    'default': dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        ssl_require=False
    )
}
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
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

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/entrar/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'


