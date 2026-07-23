"""Throwaway URLconf used ONLY via pytest-django's `@pytest.mark.urls(...)`
override in `tests/test_conformance_errors.py` — never included from
`config.urls`, never shipped in a real deployment. Exists purely to exercise
`core.exceptions.exception_handler`'s 401/403/500 branches (and, per this
fix round, the generic `APIException` branch's `AuthenticationFailed`/
`MethodNotAllowed` mapping), which have no real route in this block yet
(Stage 5, #28, is what adds real authentication that could genuinely raise
`NotAuthenticated`/`PermissionDenied`/`AuthenticationFailed`). Mirrors
backend/fastapi's own `crashing_client` fixture (tests/test_error_envelope.py)
— a throwaway crashing route added only to a fixture's own throwaway app,
never the real one."""

from __future__ import annotations

from django.urls import path
from rest_framework.authentication import BasicAuthentication
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

_CRASH_MESSAGE = "boom - a genuine bug, must never reach the client"


class _RaiseNotAuthenticatedView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request):
        raise NotAuthenticated()


class _RaisePermissionDeniedView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request):
        raise PermissionDenied()


class _CrashView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request):
        raise RuntimeError(_CRASH_MESSAGE)


class _BasicAuthOnlyView(APIView):
    """Deliberately opts BACK into `BasicAuthentication` + `IsAuthenticated`
    — the global `DEFAULT_AUTHENTICATION_CLASSES = []` (config/settings.py,
    this fix round) means no real route in this block exercises
    `AuthenticationFailed` (bad credentials) any more, so this throwaway
    view exists purely to prove `core.exceptions.exception_handler`'s
    generic `APIException` branch maps it to 401 correctly, same as
    `NotAuthenticated`."""

    permission_classes = [IsAuthenticated]
    authentication_classes = [BasicAuthentication]

    def get(self, request):
        return Response({"ok": True})


urlpatterns = [
    path("__test_only_401", _RaiseNotAuthenticatedView.as_view()),
    path("__test_only_403", _RaisePermissionDeniedView.as_view()),
    path("__test_only_crash", _CrashView.as_view()),
    path("__test_only_basic_auth", _BasicAuthOnlyView.as_view()),
]
