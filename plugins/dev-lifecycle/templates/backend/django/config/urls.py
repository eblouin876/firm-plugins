"""Root URLconf. Not vendored — standard Django project boilerplate. Stage 4
Step 2 (#27): delegates everything to `core.urls` — the DRF router +
explicit health/readyz/auth paths that reproduce the FastAPI block's route
set (see backend/fastapi/README.md's "Composition contract" EXPOSES table
for the exact route set this app converges on, and core/urls.py for the
route-by-route mapping)."""

from __future__ import annotations

from django.urls import include, path

urlpatterns: list = [
    path("", include("core.urls")),
]

__all__ = ["urlpatterns"]
