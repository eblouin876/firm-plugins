"""ASGI entrypoint. Not vendored — standard Django project boilerplate.
DRF views are synchronous (references/backend/drf.md's "The async caveat");
this module exists so the block can be served by an ASGI server (uvicorn/
gunicorn+uvicorn workers) per the compatibility matrix's Backend — Python
row, matching backend/fastapi's own ASGI-served posture, even though DRF's
own view layer stays sync underneath."""

from __future__ import annotations

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()
