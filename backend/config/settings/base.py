import os
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from corsheaders.defaults import default_headers
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = BASE_DIR.parent
env_file = os.environ.get("ENV_FILE")
load_dotenv(Path(env_file) if env_file else REPOSITORY_ROOT / ".env")


def positive_integer_setting(name, default):
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError as error:
        raise ValueError(f"{name} must be a positive integer.") from error
    if value < 1:
        raise ValueError(f"{name} must be a positive integer.")
    return value


SECRET_KEY = os.environ.get("SECRET_KEY", "development-only-change-me")
DEBUG = os.environ.get("DEBUG", "true").lower() == "true"
render_hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")
ALLOWED_HOSTS = [
    host.strip()
    for host in (
        os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
        + (f",{render_hostname}" if render_hostname else "")
    ).split(",")
    if host.strip()
]
LOCAL_DEV_ORIGINS = (
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:3002",
)
if DEBUG:
    ALLOWED_HOSTS.extend(
        host
        for host in ("localhost", "127.0.0.1")
        if host not in ALLOWED_HOSTS
    )

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "apps.accounts",
    "apps.events",
    "apps.registrations",
    "apps.tickets",
    "apps.scanning",
    "apps.audit",
    "apps.payments",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

database_url = os.environ.get("DATABASE_URL", "")
database_name = os.environ.get("DATABASE_NAME", "")
conn_max_age = int(os.environ.get("DATABASE_CONN_MAX_AGE", "600"))
if database_url:
    parsed_database_url = urlparse(database_url)
    if parsed_database_url.scheme not in {"postgres", "postgresql"}:
        raise RuntimeError("DATABASE_URL must use PostgreSQL.")
    database_name = unquote(parsed_database_url.path.lstrip("/"))
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": database_name,
            "USER": unquote(parsed_database_url.username or ""),
            "PASSWORD": unquote(parsed_database_url.password or ""),
            "HOST": parsed_database_url.hostname or "",
            "PORT": str(parsed_database_url.port or 5432),
            "CONN_MAX_AGE": conn_max_age,
            "CONN_HEALTH_CHECKS": True,
            "OPTIONS": {
                "sslmode": parse_qs(parsed_database_url.query).get(
                    "sslmode",
                    ["require"],
                )[0],
            },
        }
    }
elif database_name:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": database_name,
            "USER": os.environ.get("DATABASE_USER", ""),
            "PASSWORD": os.environ.get("DATABASE_PASSWORD", ""),
            "HOST": os.environ.get("DATABASE_HOST", "localhost"),
            "PORT": os.environ.get("DATABASE_PORT", "5432"),
            "CONN_MAX_AGE": conn_max_age,
            "CONN_HEALTH_CHECKS": True,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "development.sqlite3",
        }
    }

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
CSRF_COOKIE_SAMESITE = os.environ.get("CSRF_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SECURE = os.environ.get("CSRF_COOKIE_SECURE", "false").lower() == "true"
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
if DEBUG:
    CSRF_TRUSTED_ORIGINS.extend(
        origin
        for origin in LOCAL_DEV_ORIGINS
        if origin not in CSRF_TRUSTED_ORIGINS
    )
CORS_ALLOWED_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
if DEBUG:
    CORS_ALLOWED_ORIGINS.extend(
        origin
        for origin in LOCAL_DEV_ORIGINS
        if origin not in CORS_ALLOWED_ORIGINS
    )
CORS_ALLOW_HEADERS = (
    *default_headers,
    "idempotency-key",
    "x-proof-access-token",
)
CORS_ALLOW_CREDENTIALS = True

PAYU_MERCHANT_KEY = os.environ.get("PAYU_MERCHANT_KEY", "")
PAYU_MERCHANT_SALT = os.environ.get("PAYU_MERCHANT_SALT", "")
PAYU_ENVIRONMENT = os.environ.get("PAYU_ENVIRONMENT", "test").lower()
PAYU_SUCCESS_URL = os.environ.get("PAYU_SUCCESS_URL", "")
PAYU_FAILURE_URL = os.environ.get("PAYU_FAILURE_URL", "")
PAYU_WEBHOOK_URL = os.environ.get("PAYU_WEBHOOK_URL", "")
PAYU_FRONTEND_URL = os.environ.get("PAYU_FRONTEND_URL", "")
PAYMENT_PROOF_RESERVATION_HOURS = positive_integer_setting(
    "PAYMENT_PROOF_RESERVATION_HOURS",
    24,
)
PAYMENT_PROOF_RESUBMISSION_HOURS = positive_integer_setting(
    "PAYMENT_PROOF_RESUBMISSION_HOURS",
    12,
)
CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "").strip()
CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY", "").strip()
CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "").strip()
CLOUDINARY_PAYMENT_PROOF_FOLDER = "college-ticketing/payment-proofs"
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "25"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "false").lower() == "true"
EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", "false").lower() == "true"
EMAIL_TIMEOUT = int(os.environ.get("EMAIL_TIMEOUT", "10"))
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL",
    "Soundarya Ticketing <tickets@localhost>",
)
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")
BREVO_SENDER_EMAIL = os.environ.get("BREVO_SENDER_EMAIL", "")
BREVO_SENDER_NAME = os.environ.get(
    "BREVO_SENDER_NAME",
    "Soundarya Institute",
)
BREVO_WEBHOOK_TOKEN = os.environ.get("BREVO_WEBHOOK_TOKEN", "")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "config.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "config.pagination.StandardPagination",
    "PAGE_SIZE": 25,
    "EXCEPTION_HANDLER": "config.exceptions.api_exception_handler",
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "30/minute",
        "user": "120/minute",
    },
}

if not DEBUG:
    if not SECRET_KEY or SECRET_KEY == "development-only-change-me":
        raise RuntimeError("Set SECRET_KEY in production.")
    if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
        raise RuntimeError("Configure PostgreSQL using DATABASE_URL or DATABASE_NAME.")
    if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
        raise RuntimeError("Configure explicit ALLOWED_HOSTS in production.")
    if not CORS_ALLOWED_ORIGINS:
        raise RuntimeError("Set CORS_ALLOWED_ORIGINS to the Vercel frontend origin.")
    if not set(CORS_ALLOWED_ORIGINS).issubset(CSRF_TRUSTED_ORIGINS):
        raise RuntimeError(
            "Every CORS_ALLOWED_ORIGINS entry must also be trusted for CSRF."
        )
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SAMESITE = "None"
    CSRF_COOKIE_SAMESITE = "None"
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
