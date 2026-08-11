from pathlib import Path
import os
import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env
load_dotenv(BASE_DIR / ".env")

# ==========================
# Security
# ==========================

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "django-insecure-life-simulation-change-this-in-production-xyz123"
)

DEBUG = os.getenv("DEBUG", "False") == "True"

ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    "evolvex-i5ud.onrender.com",
    "54.89.190.207",
    "www" ".evolvexapp.com",
    "evolvexapp.com",
]

# Render sets this automatically at deploy time — covers the case where
# the actual live URL differs from the hardcoded one above (e.g. Render
# appends a suffix, or the service gets renamed/recreated).
RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME")
if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

CSRF_TRUSTED_ORIGINS = [
    "https://evolvex-i5ud.onrender.com",
    "https://evolvexapp.com",
    "https://www.evolvexapp.com",
]
if RENDER_EXTERNAL_HOSTNAME:
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

# Render terminates HTTPS at its own proxy and forwards the request to
# gunicorn as plain HTTP, adding an `X-Forwarded-Proto: https` header to
# say so. Without this line, Django can't tell the original request was
# HTTPS, so SECURE_SSL_REDIRECT below thinks every request is insecure
# and keeps trying to redirect — which on a proxy like this causes a
# redirect loop / crash instead of working normally. This tells Django
# to trust that header from Render's proxy.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ==========================
# Applications
# ==========================

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "cloudinary",

    "users",
    "tasks",
    "tracker",
    "reports",
    "diet",
    "analyzer",
    "roadmap",
    "subscriptions",
    "home",
    "pages",
]

# ==========================
# Middleware
# ==========================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",

    # WhiteNoise
    "whitenoise.middleware.WhiteNoiseMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",
    "life_simulation.middleware.SelectedDateMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "life_simulation.middleware.UserTimezoneMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "life_simulation.urls"

# ==========================
# Templates
# ==========================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "life_simulation.context_processors.header_date",
                "life_simulation.context_processors.firebase_config",
                "life_simulation.context_processors.pending_popup",
            ],
        },
    },
]

WSGI_APPLICATION = "life_simulation.wsgi.application"

# ==========================
# Database
# ==========================

DATABASE_URL = os.getenv("DATABASE_URL")

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
            ssl_require=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# ==========================
# User Model
# ==========================

AUTH_USER_MODEL = "users.CustomUser"

# ==========================
# Firebase (Google Sign-In)
# ==========================
# NOTE: Fallback defaults below match the hardcoded firebaseConfig in
# login.html. This is a temporary safety net — if your .env file is
# missing these vars (or has wrong values), FIREBASE_PROJECT_ID would
# otherwise end up as None, which breaks Firebase token verification
# on the backend (google_id_token.verify_firebase_token(..., audience=None))
# and causes the Google login flow to silently fail after consent.
#
# ⚠️ Still create/fix your .env file properly — don't rely on these
# fallbacks in production, since this file may get committed to git.

FIREBASE_API_KEY = os.getenv(
    "FIREBASE_API_KEY",
    "AIzaSyBlmXCTnb58amqLoh2cTnn6lF65A4LT294"
)
FIREBASE_AUTH_DOMAIN = os.getenv(
    "FIREBASE_AUTH_DOMAIN",
    "finalevolve.firebaseapp.com"
)
FIREBASE_PROJECT_ID = os.getenv(
    "FIREBASE_PROJECT_ID",
    "finalevolve"
)
FIREBASE_STORAGE_BUCKET = os.getenv(
    "FIREBASE_STORAGE_BUCKET",
    "finalevolve.firebasestorage.app"
)
FIREBASE_MESSAGING_SENDER_ID = os.getenv(
    "FIREBASE_MESSAGING_SENDER_ID",
    "1088279829574"
)
FIREBASE_APP_ID = os.getenv(
    "FIREBASE_APP_ID",
    "1:1088279829574:web:fa40c73a973b065cdebe47"
)

FIREBASE_WEB_CONFIG = {
    "apiKey": FIREBASE_API_KEY,
    "authDomain": FIREBASE_AUTH_DOMAIN,
    "projectId": FIREBASE_PROJECT_ID,
    "storageBucket": FIREBASE_STORAGE_BUCKET,
    "messagingSenderId": FIREBASE_MESSAGING_SENDER_ID,
    "appId": FIREBASE_APP_ID,
}


# ==========================
# Authentication
# ==========================

LOGIN_URL = "/users/login/"
LOGIN_REDIRECT_URL = "/reports/"
LOGOUT_REDIRECT_URL = "/users/login/"

# ==========================
# Password Validators
# ==========================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"
    },
]

# ==========================
# Localization
# ==========================

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"

USE_I18N = True
USE_TZ = True

# ==========================
# Static Files
# ==========================

STATIC_URL = "/static/"

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

STATIC_ROOT = BASE_DIR / "staticfiles"

# NOTE: static storage backend is now declared in the STORAGES dict
# further down (next to CLOUDINARY_STORAGE) instead of here, to avoid
# conflicting with cloudinary_storage's collectstatic override — see
# the comment there for details.

# ── Dev convenience: serve static files straight from STATICFILES_DIRS
# instead of requiring `collectstatic` + the compressed manifest on every
# change (that manifest is also what was making collectstatic feel like
# it "resets" your CSS — it was serving an old cached-and-hashed copy).
# Safe to leave on locally; for production (Render) this should stay
# False so the optimized/cached manifest build is used instead. ──
WHITENOISE_USE_FINDERS = DEBUG
WHITENOISE_AUTOREFRESH = DEBUG

# ==========================
# Media Files
# ==========================

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Cloudinary — used as the actual storage backend for MEDIA files (boss
# portraits, avatars, etc). Render's filesystem is ephemeral (wiped on
# every deploy/restart), so local disk storage doesn't survive there.
# Cloudinary keeps uploaded/generated images permanently, and works
# identically on localhost and on Render — no DEBUG-based branching needed.
CLOUDINARY_STORAGE = {
    "CLOUD_NAME": os.getenv("CLOUDINARY_CLOUD_NAME"),
    "API_KEY": os.getenv("CLOUDINARY_API_KEY"),
    "API_SECRET": os.getenv("CLOUDINARY_API_SECRET"),
}

# Use Django's unified STORAGES setting instead of the old separate
# DEFAULT_FILE_STORAGE / STATICFILES_STORAGE settings. This is required
# here because cloudinary_storage's collectstatic override checks
# STATICFILES_STORAGE and silently skips copying any static files unless
# it matches Cloudinary's own static storage class — which broke WhiteNoise
# entirely (0 files copied, CSS/JS 404s in production). Declaring both
# backends explicitly in STORAGES keeps WhiteNoise serving static files
# while Cloudinary handles only MEDIA (uploaded/generated images).
STORAGES = {
    "default": {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# ==========================
# Email
# ==========================
# Switched from smtp.gmail.com to Brevo's relay. Gmail's SMTP server
# resolves to an IPv6 address, and Render's outbound network doesn't
# route IPv6 properly — that's what caused "[Errno 101] Network is
# unreachable" here, not a credentials problem. Brevo's relay works
# reliably from Render.
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp-relay.brevo.com")
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")          # Brevo SMTP login (your Brevo account email)
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")  # Brevo SMTP key, NOT your account password
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER)  # must be a Brevo-verified sender
# Without this, a blocked/slow outbound SMTP connection on Render hangs
# forever — gunicorn's own timeout then SIGKILLs the worker mid-request,
# which is what was causing "Internal Server Error" on complete-profile.
# 10s is generous for a normal SMTP handshake; it lets the existing
# try/except around send_mail() in users/views.py actually catch the
# failure and show a friendly error instead of killing the whole worker.
EMAIL_TIMEOUT = 10

# ==========================
# Default PK
# ==========================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Cookie & transport security ──────────────────────────────────────
# These must be True in production (HTTPS) so session/CSRF cookies can
# never be sent over plain HTTP, and browsers are forced onto HTTPS.
# They're tied to DEBUG so local development (plain http://127.0.0.1)
# still works without cookies silently failing to be set.
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # must stay False: JS needs to read this token to send it back

SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 0 if DEBUG else 31536000  # 1 year, only once confirmed working on HTTPS
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# ── Fix for Firebase signInWithPopup ──────────────────────────────────
# Django's SecurityMiddleware sends "Cross-Origin-Opener-Policy: same-origin"
# by default, which blocks the Firebase Auth popup from communicating back
# to the parent window. Symptom: popup opens, consent completes, popup
# closes, but the JS promise never resolves — looks like it "loads then
# cancels". This setting relaxes that header so the popup flow works.
SECURE_CROSS_ORIGIN_OPENER_POLICY = "unsafe-none"

# ==========================
# Subscriptions — Razorpay + PayPal
# ==========================
# Get these from:
#   Razorpay: https://dashboard.razorpay.com/app/keys (Test mode keys start with rzp_test_)
#   PayPal:   https://developer.paypal.com/dashboard/applications (create a Sandbox app first)

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")

PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "")
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")  # "sandbox" while testing, "live" for real payments

# ==========================
# Logging
# ==========================
# Without this, unhandled exceptions in production (DEBUG=False) get
# swallowed by gunicorn's access-log-only output — you'd only see the
# "500" status line, never the actual Python traceback. This makes full
# tracebacks show up in Render's Logs tab regardless of DEBUG, so you
# don't need to flip DEBUG=True (and expose stack traces to visitors)
# just to see what broke.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": True,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "ERROR",
    },
}