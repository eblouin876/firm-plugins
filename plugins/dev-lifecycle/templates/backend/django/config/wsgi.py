"""WSGI entrypoint. Not vendored — standard Django project boilerplate.
Included alongside asgi.py as the conventional sync-server fallback
(gunicorn's default sync worker) — see pyproject.toml's `gunicorn` dev
dependency and this block's README, "Composition contract"."""

from __future__ import annotations

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
