"""`core` app's URLconf — Stage 4 Step 2 (#27): the DRF router + explicit
paths that reproduce backend/fastapi's route set (see that block's
README.md "Composition contract" EXPOSES table). Included from
`config.urls`'s root urlpatterns."""

from __future__ import annotations

from django.urls import path
from rest_framework.routers import SimpleRouter

from core.views import (
    HealthCheckView,
    ItemViewSet,
    LoginView,
    MeView,
    ReadinessCheckView,
    RefreshView,
)

# `trailing_slash=False`: backend/fastapi's contract has no trailing slash
# on any route (`/items`, `/items/{item_id}`) — matching that exactly here,
# rather than DRF's own router default (`trailing_slash=True`), is part of
# this block's wire-contract-identity target (README.md "Conformance").
router = SimpleRouter(trailing_slash=False)
router.register("items", ItemViewSet, basename="item")

urlpatterns = [
    path("health", HealthCheckView.as_view(), name="health"),
    path("readyz", ReadinessCheckView.as_view(), name="readyz"),
    path("auth/login", LoginView.as_view(), name="auth-login"),
    path("auth/refresh", RefreshView.as_view(), name="auth-refresh"),
    path("auth/me", MeView.as_view(), name="auth-me"),
    *router.urls,
]

__all__ = ["urlpatterns"]
