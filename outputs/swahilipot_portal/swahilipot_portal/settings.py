from pathlib import Path
import os

# ── Load .env file if it exists (no extra packages needed) ────────────────
_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _, _val = _line.partition("=")
            os.environ.setdefault(_key.strip(), _val.strip())

try:
    import dj_database_url
except ImportError:
    dj_database_url = None

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-change-me")
DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() in {"1", "true", "yes"}
ALLOWED_HOSTS = [h for h in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "attendance",
    "communication",
    "tasks",
    "events",
    "suggestions",
    "dashboard",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Single-login: expires stale sessions when the user logs in elsewhere
    "core.middleware.SingleLoginMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "swahilipot_portal.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": [
            "django.template.context_processors.debug",
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
            "communication.context_processors.unread_notifications",
        ]},
    }
]

WSGI_APPLICATION = "swahilipot_portal.wsgi.application"

if dj_database_url:
    DATABASES = {"default": dj_database_url.config(default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}", conn_max_age=600)}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard:home"
LOGOUT_REDIRECT_URL = "login"

# ── Email ─────────────────────────────────────────────────────────────────
# Set DJANGO_EMAIL_HOST_USER and DJANGO_EMAIL_HOST_PASSWORD in your .env file
# to enable real email sending (e.g. Gmail SMTP with an App Password).
#
# How to get a Gmail App Password (one-time setup):
#   1. Sign in to https://myaccount.google.com
#   2. Security → 2-Step Verification → turn ON if not already
#   3. Visit https://myaccount.google.com/apppasswords
#   4. Select Mail / Windows Computer → Generate
#   5. Copy the 16-char password → paste as DJANGO_EMAIL_HOST_PASSWORD in .env
#
# ── Testing email locally ─────────────────────────────────────────────────
# If DJANGO_EMAIL_HOST_USER / DJANGO_EMAIL_HOST_PASSWORD are NOT set in .env,
# the system automatically falls back to the CONSOLE backend.
#
# In console mode:
#   - No email is actually sent.
#   - The full password-reset email (including the reset link) is printed
#     directly to the terminal window where you ran `python manage.py runserver`.
#   - Copy the link from the terminal and paste it into your browser to
#     complete the password reset — it works exactly like a real email.
#
_email_user     = os.getenv("DJANGO_EMAIL_HOST_USER", "").strip()
_email_password = os.getenv("DJANGO_EMAIL_HOST_PASSWORD", "").strip()

EMAIL_HOST          = "smtp.gmail.com"
EMAIL_PORT          = 587
EMAIL_USE_TLS       = True
EMAIL_USE_SSL       = False
EMAIL_HOST_USER     = _email_user
EMAIL_HOST_PASSWORD = _email_password
DEFAULT_FROM_EMAIL  = (
    f"Swahilipot Hub Portal <{_email_user}>" if _email_user
    else "Swahilipot Hub Portal <noreply@swahilipothub.co.ke>"
)
SERVER_EMAIL = _email_user or "noreply@swahilipothub.co.ke"

# Use real SMTP only when both user and password are provided; otherwise console
if _email_user and _email_password:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
X_FRAME_OPTIONS = "DENY"
