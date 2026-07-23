"""DRF views — Stage 4 Step 2 (#27), the contract-emission layer. Mirrors
`backend/fastapi`'s `app/api/routers/{items,health,auth}.py` handler-for-
handler; see each view's own docstring for the specific behavior it
reproduces and this block's README, "Conformance", for the wire-identity
target these routes work toward.

Wiring (Step 2 scope) stops at status codes + JSON bodies. Auth
(`permission_classes`) is deliberately `AllowAny` everywhere below — Stage 5
(#28) is what adds real authentication; every `AllowAny` here is an
explicit, documented choice (matching `backend/fastapi`'s items/health
routers having no `Depends(get_current_principal)` yet), never a bare
omission (references/backend/drf.md's "Permissions & queryset scoping":
"Never leave an endpoint AllowAny by omission")."""

from __future__ import annotations

from django.db import connection
from django.db.utils import Error as DjangoDBError
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.contract.errors import NotFoundError
from core.models import Item
from core.serializers import (
    HealthStatusSerializer,
    ItemCreateSerializer,
    ItemOutSerializer,
    ItemUpdateSerializer,
    LoginRequestSerializer,
    ReadinessStatusSerializer,
    RefreshRequestSerializer,
)

# JUDGMENT CALL (mirrors app/api/routers/auth.py's own, identical call):
# these 501s are a plain `{"detail": ...}` body, deliberately bypassing
# core.contract.errors.ErrorEnvelope — `ErrorCode` is a LOCKED, versioned
# enum with no `not_implemented` member, and adding one for a temporary
# stub is exactly the kind of contract change that module's own docstring
# says needs the same coordination as any other wire-shape edit. Returning
# a plain `Response(...)` here (never raising) also means this never
# touches `core.exceptions.exception_handler` at all — the bypass is
# structural, not just a documented intent.
_STUB_DETAIL = "Not implemented — lands in Stage 5 (#28)."


class ItemViewSet(viewsets.ModelViewSet):
    """Full CRUD for `Item` — the DRF counterpart to backend/fastapi's
    `app/api/routers/items.py`. Every handler below is thin: validate (via
    the serializer DRF already ran), delegate to the ORM, map to
    `ItemOutSerializer`, return — same shape as the FastAPI router's own
    "validate, delegate, map, return" pattern.

    `queryset = Item.objects.all()` already excludes soft-deleted rows —
    `Item.objects` is `ItemManager`, scoped through `ItemQuerySet.
    not_deleted()` by default (core/models.py) — so `list`/`retrieve`
    (and this class's own `get_object` override below) never need to
    repeat that filter by hand.

    ACCEPTED DIVERGENCE (documented, not forced — see this block's README,
    "Conformance"): `ModelViewSet` + a router also exposes `PUT
    /items/{item_id}` (full replace) via `update()`, which
    `packages/api-client/openapi.json` does not define (FastAPI's `items`
    router only has PATCH). `update()` is overridden below to always apply
    partial semantics regardless of PUT vs PATCH — `ItemUpdateSerializer`
    already declares every field optional, matching the contract's
    PATCH-only `ItemUpdate` shape — so a stray PUT behaves identically to
    PATCH rather than silently nulling out omitted fields; a client
    generated from the frozen `openapi.json` simply never calls PUT."""

    queryset = Item.objects.all()
    permission_classes = [AllowAny]

    def get_serializer_class(self):
        if self.action == "create":
            return ItemCreateSerializer
        if self.action in {"update", "partial_update"}:
            return ItemUpdateSerializer
        return ItemOutSerializer

    def get_object(self):
        """Overrides DRF's default (`get_object()` normally raises a bare
        `Http404`) so a missing item renders the SAME message text
        backend/fastapi's `NotFoundError(f"Item {item_id} was not
        found.")` uses (app/api/routers/items.py's `get_item`/
        `update_item`/`delete_item`) — this is what lets the
        conformance-proof tests build the expected envelope straight from
        `core.contract.errors.NotFoundError` and assert byte-equality
        against what this view actually sends, not just "some 404"."""
        pk = self.kwargs[self.lookup_url_kwarg or self.lookup_field]
        try:
            return self.get_queryset().get(pk=pk)
        except (Item.DoesNotExist, ValueError, TypeError):
            # ValueError/TypeError: a malformed (non-UUID) `item_id` —
            # Django's UUIDField lookup raises this rather than
            # `DoesNotExist` for a value that isn't a well-formed UUID at
            # all. FastAPI's path-typed `item_id: uuid.UUID` would instead
            # reject that at 422 (a routing-level type mismatch) before
            # the handler ever runs — a second, smaller accepted
            # per-framework divergence alongside the one this block's
            # README already documents for PageParams `extra="forbid"`.
            # Treating it as "not found" here (404) rather than
            # "unvalidatable" (422) is the more conservative of the two
            # readings for an ID a caller already has no way to have
            # gotten right, and keeps this override's error path single
            # (one exception type raised, not two).
            raise NotFoundError(f"Item {pk} was not found.") from None

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(ItemOutSerializer(serializer.instance).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(ItemOutSerializer(serializer.instance).data)

    def perform_destroy(self, instance):
        """Soft-delete via `Item.mark_deleted()`, mirroring backend/
        fastapi's `AsyncRepository.delete()` semantics for this model (see
        that repository's own delete implementation and core/models.py's
        module docstring) — a row disappears from every default-manager
        lookup, this is NOT a hard SQL `DELETE`."""
        instance.mark_deleted()
        instance.save(update_fields=["deleted_at"])


class HealthCheckView(APIView):
    """`GET /health` — liveness only, touches nothing but the process
    itself (no DB), matching backend/fastapi's `app/api/routers/
    health.py`'s `health_check` and its own docstring on why liveness
    must not depend on the database."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request):
        return Response(HealthStatusSerializer({"status": "ok"}).data)


class ReadinessCheckView(APIView):
    """`GET /readyz` — readiness: runs a real `SELECT 1` against the
    configured database, mirroring backend/fastapi's `readiness_check`.
    `django.db.utils.Error` is the base of Django's whole DB-exception
    hierarchy (`OperationalError`, `InterfaceError`, ...) — caught
    specifically, the same "a real DB-connectivity failure, not a bare
    `except Exception`" posture the FastAPI sibling documents, so a
    genuine application bug inside this view still surfaces as an
    unhandled 500 via `core.exceptions.exception_handler`'s catch-all
    instead of being misreported as "DB down".

    A DB-down response is a plain `ReadinessStatus(status="unavailable")`
    body at 503, NOT `ErrorEnvelope` — same judgment call backend/
    fastapi's `health.py` documents: `ErrorCode` has no
    `service_unavailable` member, and an orchestrator polls this by status
    code, not by envelope shape."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except DjangoDBError:
            return Response(
                ReadinessStatusSerializer({"status": "unavailable"}).data,
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(ReadinessStatusSerializer({"status": "ready"}).data)


class LoginView(APIView):
    """`POST /auth/login` — stub. Validates the request body against
    `LoginRequestSerializer` (so a malformed body still 422s, matching
    FastAPI validating `LoginRequest` before its own stub handler ever
    runs) then unconditionally returns the plain 501 stub body — see this
    module's `_STUB_DETAIL` docstring for why that bypasses
    `ErrorEnvelope`."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def post(self, request):
        serializer = LoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({"detail": _STUB_DETAIL}, status=status.HTTP_501_NOT_IMPLEMENTED)


class RefreshView(APIView):
    """`POST /auth/refresh` — stub. See `LoginView`."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def post(self, request):
        serializer = RefreshRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({"detail": _STUB_DETAIL}, status=status.HTTP_501_NOT_IMPLEMENTED)


class MeView(APIView):
    """`GET /auth/me` — stub, the bearer-scheme seam. `permission_classes
    = [AllowAny]` deliberately: mirrors backend/fastapi's
    `get_current_principal` dependency, which unconditionally raises 501
    (`auto_error=False` on its own `HTTPBearer` instance) rather than
    gating behind a real auth check that doesn't exist yet — see that
    dependency's own docstring ("fails closed with a 501, not yet a
    401/403, because the check itself doesn't exist yet").

    The `HTTPBearer` security scheme itself (`openapi.json`'s
    `securitySchemes.HTTPBearer`) is a later step's concern: no
    drf-spectacular schema view is wired yet (this block's README,
    "Conformance" — Step 1 already noted `drf-spectacular` is installed
    with no `SPECTACULAR_SETTINGS`/schema view). This view's job for Step
    2 is only the wire behavior (501, no body validation needed — `/me`
    takes no request body), not registering the scheme in a served
    schema."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request):
        return Response({"detail": _STUB_DETAIL}, status=status.HTTP_501_NOT_IMPLEMENTED)
