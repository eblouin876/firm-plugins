"""This block's Django settings module. Not a vendored file — new glue,
env-driven per this block's composition contract (see README.md "Composition
contract"). Every value that varies per-environment is read from process env
via `os.environ`, matching `secrets-loading/secret_store.py`'s "process env
first" posture (`core/contract/secret_store.py`, vendored below) rather than
Django's own `django-environ`/python-decouple conventions — this block has no
dependency on either.

**REST_FRAMEWORK is a placeholder as of this step.** `DEFAULT_RENDERER_CLASSES`
is pinned to JSON-only now (references/backend/drf.md's "Browsable API": drop
`BrowsableAPIRenderer` in prod); the custom `EXCEPTION_HANDLER` that maps DRF's
own exceptions onto `core.contract.errors.ErrorEnvelope`, and the
`DEFAULT_PAGINATION_CLASS` that emits `core.contract.pagination.Page`'s
`{items, total, page, size, pages}` shape, are Step 2's job — see the `TODO`
comments inline and this block's README, "Conformance"."""

from __future__ import annotations

import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Core / security — every value env-driven, no hardcoded secret or default
# that would be unsafe left in place in production.
# ---------------------------------------------------------------------------


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


try:
    SECRET_KEY = os.environ["SECRET_KEY"]
except KeyError as exc:
    raise RuntimeError(
        "SECRET_KEY is required and must be set via the process environment "
        "(never hardcoded here) — see this block's README, 'Composition "
        "contract'. Generate one with: "
        "python -c \"from django.core.management.utils import "
        "get_random_secret_key; print(get_random_secret_key())\""
    ) from exc

# Default False: a missing/unset DEBUG env var must never silently enable
# debug mode in an environment that forgot to set it (the unsafe default
# would be `True`; this block deliberately inverts that).
DEBUG = _env_bool("DEBUG", False)

ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]


# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    # No admin/sessions/messages/staticfiles: this is an API-only block (JSON
    # over DRF) with no server-rendered templates or admin site as of this
    # step — add them back if a materialized project needs the admin site.
    "rest_framework",
    # drf-spectacular is installed (pyproject.toml, matrix-pinned) for the
    # OpenAPI 3 schema generation a later step wires; no DEFAULT_SCHEMA_CLASS
    # is set yet — see the REST_FRAMEWORK TODO below.
    "drf_spectacular",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# ---------------------------------------------------------------------------
# Database — Postgres via psycopg (Django 5.2 prefers psycopg 3; the
# `django.db.backends.postgresql` engine auto-detects whichever of
# psycopg2/psycopg is installed — see references/compatibility-matrix.md's
# "Backend — Django track" psycopg row). DATABASE_URL is required, no
# default: a missing value fails `Settings`/app boot immediately (mirrors
# backend/fastapi's `AppSettings.database_url` posture), not on the first
# request that touches the database.
# ---------------------------------------------------------------------------

if not os.environ.get("DATABASE_URL"):
    raise RuntimeError(
        "DATABASE_URL is required (a postgres:// URL in dev/prod) — see this "
        "block's README, 'Composition contract'. Hermetic checks/tests that "
        "need no real server use config.settings_test instead "
        "(DJANGO_SETTINGS_MODULE=config.settings_test)."
    )

DATABASES = {
    "default": dj_database_url.config(
        env="DATABASE_URL",
        conn_max_age=600,
        # Not forced True: a local/dev Postgres often has no TLS listener at
        # all. A production DATABASE_URL should append `?sslmode=require`
        # itself rather than have this block force it kit-wide.
        ssl_require=False,
    ),
}


# ---------------------------------------------------------------------------
# Password validation — Django defaults; this block has no custom user model
# or auth flow yet (out of scope for this step).
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# ---------------------------------------------------------------------------
# Default primary key field type
# ---------------------------------------------------------------------------

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ---------------------------------------------------------------------------
# Transport security headers — DELIBERATELY not set here (Stage 4 Step 2,
# #27). HSTS (SECURE_HSTS_SECONDS), nosniff (SECURE_CONTENT_TYPE_NOSNIFF),
# SSL-redirect (SECURE_SSL_REDIRECT), and referrer-policy
# (SECURE_REFERRER_POLICY) are Django's own settings-driven equivalents of
# what backend/fastapi's vendored `security-headers` component
# (app/core/security/security_headers/) stamps onto every response via
# middleware — see that component's README for the exact header set. This
# block does not vendor/wire that (or an equivalent) component yet — Step 3
# of this stage is where a security-headers component gets wired for the
# Django track, the same way Stage 3's Step 3b wired it for FastAPI
# (app/main.py's "Security composition" docstring). Setting Django's own
# SECURE_* values here NOW, ahead of that, would double-stamp the same
# headers from two uncoordinated sources once Step 3 lands its own
# middleware/component — so they are deliberately left unset in this step.
# A PRODUCTION MATERIALIZATION OF THIS BLOCK MUST WIRE THAT COMPONENT (or,
# until it exists, set Django's own SECURE_* values itself) — shipping
# without either leaves every response without HSTS/nosniff/frame-options/
# referrer-policy protection. See README.md, "Conformance" / "Security".
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Django REST Framework — PLACEHOLDER as of this step (Stage 4 Step 2,
# #27 routes/serializers commit). JSONRenderer-only is locked in now; the
# custom EXCEPTION_HANDLER and DEFAULT_PAGINATION_CLASS that make this
# app's wire responses match the FastAPI block byte-for-byte are this same
# step's NEXT commit — see this block's README, "Conformance", and
# error-envelope/errors.py + pagination/schema.py's own module docstrings
# for the shapes they must reproduce.
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    # TODO(Stage 4 Step 2, #27): map DRF's own exception types (ValidationError,
    # NotFound, PermissionDenied, NotAuthenticated, Throttled, ...) onto
    # core.contract.errors.ErrorEnvelope via a custom EXCEPTION_HANDLER, so this
    # app's error responses are wire-identical to the FastAPI block's — see
    # core/contract/errors.py's module docstring ("ONE error shape, not two").
    # "EXCEPTION_HANDLER": "core.exceptions.exception_handler",
    # TODO(Stage 4 Step 2, #27): DRF's built-in PageNumberPagination emits
    # {count, next, previous, results} — NOT this contract's {items, total,
    # page, size, pages} shape (core.contract.pagination.Page). Wire a custom
    # pagination class that emits the latter before enabling this.
    # "DEFAULT_PAGINATION_CLASS": "core.pagination.ContractPageNumberPagination",
    # "PAGE_SIZE": 20,
}
