"""Root URLconf. Not vendored — standard Django project boilerplate. Stage 4
Step 2 (#27): delegates everything to `core.urls` — the DRF router +
explicit health/readyz/auth paths that reproduce the FastAPI block's route
set (see backend/fastapi/README.md's "Composition contract" EXPOSES table
for the exact route set this app converges on, and core/urls.py for the
route-by-route mapping).

Stage 4 Step 4 (#27) adds `/api/schema` — drf-spectacular's `SpectacularAPIView`,
serving the same OpenAPI document `manage.py spectacular --file <path>`
exports (README.md, "Conformance"). Not part of the frozen wire contract
itself (`packages/api-client/openapi.json` has no self-describing schema
route), so it's NOT under `core.urls`'s router/path set — a separate,
additive path this block's own conformance tooling and a project's
interactive API browsing use, matching drf-spectacular's own documented
convention for where this view lives in a project's URLconf."""

from __future__ import annotations

from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

urlpatterns: list = [
    path("api/schema", SpectacularAPIView.as_view(), name="schema"),
    path("", include("core.urls")),
]

__all__ = ["urlpatterns"]
