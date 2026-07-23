"""`core` app's URLconf — Stage 4 Step 2 (#27): the DRF router + explicit
paths that reproduce backend/fastapi's route set (see that block's
README.md "Composition contract" EXPOSES table). Included from
`config.urls`'s root urlpatterns."""

from __future__ import annotations

from django.urls import path
from rest_framework.routers import SimpleRouter

from core.views import (
    AdminPingView,
    AdminUserBanView,
    AdminUserDetailView,
    AdminUserForceVerifyView,
    AdminUserListView,
    AdminUserReinstateView,
    AdminUserRolesView,
    AdminUserSuspendView,
    HealthCheckView,
    ItemViewSet,
    LoginView,
    LogoutView,
    MeView,
    ReadinessCheckView,
    RefreshView,
    RegisterView,
    RequestPasswordResetView,
    ResetPasswordView,
    VerifyEmailView,
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
    path("auth/register", RegisterView.as_view(), name="auth-register"),
    path("auth/login", LoginView.as_view(), name="auth-login"),
    path("auth/refresh", RefreshView.as_view(), name="auth-refresh"),
    path("auth/logout", LogoutView.as_view(), name="auth-logout"),
    path("auth/me", MeView.as_view(), name="auth-me"),
    path("auth/verify-email", VerifyEmailView.as_view(), name="auth-verify-email"),
    path(
        "auth/request-password-reset",
        RequestPasswordResetView.as_view(),
        name="auth-request-password-reset",
    ),
    path("auth/reset-password", ResetPasswordView.as_view(), name="auth-reset-password"),
    # Stage 5d (#46): the RBAC admin example -- see core/views.py's
    # AdminPingView for what it demonstrates and why it needs no new auth
    # logic of its own.
    path("admin/ping", AdminPingView.as_view(), name="admin-ping"),
    # Stage 13b: admin user management -- see core/views.py's own
    # module-level comment for the full design. `<str:user_id>`, NOT
    # Django's `<uuid:...>` converter -- see `_get_admin_user`'s own
    # docstring for why a plain string segment (validated by hand, inside
    # DRF's exception-handler cycle) is required for a malformed id to
    # still render THIS block's ErrorEnvelope rather than Django's raw,
    # unenveloped routing-level 404.
    path("admin/users", AdminUserListView.as_view(), name="admin-user-list"),
    path("admin/users/<str:user_id>", AdminUserDetailView.as_view(), name="admin-user-detail"),
    path("admin/users/<str:user_id>/suspend", AdminUserSuspendView.as_view(), name="admin-user-suspend"),
    path("admin/users/<str:user_id>/ban", AdminUserBanView.as_view(), name="admin-user-ban"),
    path("admin/users/<str:user_id>/reinstate", AdminUserReinstateView.as_view(), name="admin-user-reinstate"),
    path("admin/users/<str:user_id>/roles", AdminUserRolesView.as_view(), name="admin-user-roles"),
    path(
        "admin/users/<str:user_id>/force-verify",
        AdminUserForceVerifyView.as_view(),
        name="admin-user-force-verify",
    ),
    *router.urls,
]

__all__ = ["urlpatterns"]
