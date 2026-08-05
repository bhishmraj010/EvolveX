from pathlib import Path
import os
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
    "life-simulation-9bqz.onrender.com",
]

CSRF_TRUSTED_ORIGINS = [
    "https://life-simulation-9bqz.onrender.com",
]

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

    "users",
    "tasks",
    "tracker",
    "reports",
    "diet",
    "analyzer",
    "roadmap",
    "subscriptions",
    "home",
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

# Debug print at startup so you can immediately see in the terminal
# whether these values loaded correctly (remove once confirmed working).
print(f"[DEBUG] FIREBASE_PROJECT_ID = {FIREBASE_PROJECT_ID}")


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

STATICFILES_STORAGE = (
    "whitenoise.storage.CompressedManifestStaticFilesStorage"
)

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

# ==========================
# Email
# ==========================

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER)

# ==========================
# Default PK
# ==========================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Temporary session/cookie settings for local testing ──
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'

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