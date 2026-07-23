"""DRF views — Stage 4 Step 2 (#27), the contract-emission layer, with the
`/auth/*` views given real behavior in Stage 5b (#44). Mirrors
`backend/fastapi`'s `app/api/routers/{items,health,auth}.py` handler-for-
handler; see each view's own docstring for the specific behavior it
reproduces and this block's README, "Conformance", for the wire-identity
target these routes work toward.

`items`/`health`/`readyz` wiring (Step 2 scope) stops at status codes +
JSON bodies; their `permission_classes` stay `AllowAny` deliberately (Stage
5, #28, only ever scoped to `/auth/*` -- see `README.md`'s own Stage 5
scope note), matching `backend/fastapi`'s items/health routers having no
`Depends(get_current_principal)` either, never a bare omission
(references/backend/drf.md's "Permissions & queryset scoping": "Never
leave an endpoint AllowAny by omission").

The five `/auth/*` views below ARE the real behavior: each validates its
request body via the matching serializer (DRF's own `is_valid(raise_
exception=True)` -- a malformed body still 422s, mapped by `core.
exceptions.exception_handler`'s `ValidationError` branch), builds a fresh
`AuthService` via `core.security.auth.stores.build_auth_service()`, and
bridges into that service's async methods with `asgiref.sync.
async_to_sync(...)` -- every one of these views is an ordinary SYNC DRF
`APIView` method (`def`, not `async def`), the same "sync view, async
service, bridged at the call site" posture `stores.py`'s own module
docstring documents. Every raised `_core.AuthError` (`InvalidCredentials`,
`InvalidToken`, `TokenReused`, `EmailAlreadyExists`) is left UNCAUGHT here
-- `core/exceptions.py`'s `exception_handler` maps the whole hierarchy onto
`ErrorEnvelope`, mirroring `app/main.py`'s `_auth_error_handler` on the
FastAPI track. No view below ever constructs an `ErrorEnvelope`/`AppError`
itself, same posture `app/api/routers/auth.py`'s own module docstring
documents for its FastAPI counterparts."""

from __future__ import annotations

import uuid

from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connection
from django.db.utils import Error as DjangoDBError
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.contract.errors import NotFoundError
from core.models import Item
from core.security.auth import AuthService, InvalidToken, resolve_principal
from core.security.auth.stores import (
    AuditAuthEventSink,
    DjangoRefreshTokenStore,
    DjangoUserStore,
    build_auth_service,
    build_lockout_policy,
    get_password_service,
    get_token_service,
    utc_now,
)
from core.serializers import (
    ErrorEnvelopeSerializer,
    HealthStatusSerializer,
    ItemCreateSerializer,
    ItemOutSerializer,
    ItemUpdateSerializer,
    LoginRequestSerializer,
    PrincipalOutSerializer,
    ReadinessStatusSerializer,
    RefreshRequestSerializer,
    RegisterRequestSerializer,
    TokenResponseSerializer,
)


def _build_login_auth_service() -> AuthService:
    """Stage 5c (#45): the LOGIN-GATED `AuthService` — same store/service
    composition `core.security.auth.stores.build_auth_service()` uses
    (fresh `DjangoUserStore`/`DjangoRefreshTokenStore`, the process-wide
    `get_password_service()`, a fresh `get_token_service()`, `utc_now` as
    the shared clock), PLUS `lockout=build_lockout_policy()`,
    `require_verification=settings.AUTH_REQUIRE_EMAIL_VERIFICATION`, and
    `events=AuditAuthEventSink()` — mirroring `backend/fastapi`'s
    `app/api/deps.py:get_auth_service`'s own Stage 5c wiring exactly.

    Built here at the view call site, not inside `build_auth_service()`
    itself (Agent A's factory — deliberately left unchanged this stage;
    see that function's own docstring: "wiring `AuthService`'s own new
    keyword parameters into `LoginView`/`RegisterView` ... is Agent B's
    job"). `build_lockout_policy()` is called fresh here — same
    `DjangoLockoutStore`-backed table `core.security.auth.stores.
    build_account_service()`'s own `lockout=build_lockout_policy()` call
    reads/writes (Django's async ORM has no per-request session object to
    share the way `backend/fastapi`'s `AsyncSession` does — see
    `build_lockout_policy`'s own docstring — so "the same policy" here
    means "the same underlying table", which is what actually matters:
    a lockout `LoginView` records is visible to, and can be lifted by, a
    later `AccountService.reset_password` call built from a completely
    separate `build_lockout_policy()` invocation).

    `RegisterView` deliberately does NOT use this — `AuthService.register`
    never consults `lockout`/`require_verification`/`events` at all (see
    `_core.AuthService.register`'s own docstring), so the plain, unwired
    `build_auth_service()` remains the right (and simpler) choice there."""
    return AuthService(
        users=DjangoUserStore(),
        refresh_tokens=DjangoRefreshTokenStore(),
        passwords=get_password_service(),
        tokens=get_token_service(),
        now=utc_now,
        lockout=build_lockout_policy(),
        require_verification=settings.AUTH_REQUIRE_EMAIL_VERIFICATION,
        events=AuditAuthEventSink(),
    )

# Stage 4 Step 4 (#27): every `operation_id`/`tags` value below is set to
# the EXACT string `packages/api-client/openapi.json` (the frozen FastAPI
# contract) already uses for the same operation — FastAPI auto-derives its
# operationIds from `{handler_name}_{path}_{method}` (see that file's own
# `operationId` values); drf-spectacular has no equivalent auto-derivation
# from a DRF view/action name that would land on the same string, so this
# block sets them explicitly rather than accepting spectacular's own
# default naming. This is what gets this block's exported schema to FULL
# operationId parity (not just best-effort) with the frozen contract — see
# README.md, "Conformance", and tests/test_schema_conformance.py for the
# proof.

@extend_schema_view(
    list=extend_schema(
        operation_id="list_items_items_get",
        tags=["items"],
        responses={200: ItemOutSerializer, 422: ErrorEnvelopeSerializer},
    ),
    create=extend_schema(
        operation_id="create_item_items_post",
        tags=["items"],
        request=ItemCreateSerializer,
        responses={201: ItemOutSerializer, 422: ErrorEnvelopeSerializer},
    ),
    retrieve=extend_schema(
        operation_id="get_item_items__item_id__get",
        tags=["items"],
        responses={200: ItemOutSerializer, 404: ErrorEnvelopeSerializer, 422: ErrorEnvelopeSerializer},
    ),
    partial_update=extend_schema(
        operation_id="update_item_items__item_id__patch",
        tags=["items"],
        request=ItemUpdateSerializer,
        responses={200: ItemOutSerializer, 404: ErrorEnvelopeSerializer, 422: ErrorEnvelopeSerializer},
    ),
    destroy=extend_schema(
        operation_id="delete_item_items__item_id__delete",
        tags=["items"],
        responses={204: None, 404: ErrorEnvelopeSerializer, 422: ErrorEnvelopeSerializer},
    ),
)
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

    `http_method_names` below deliberately excludes `"put"`: `ModelViewSet`
    + a router would otherwise also expose `PUT /items/{item_id}` (full
    replace) via `update()`, which `packages/api-client/openapi.json` does
    not define (FastAPI's `items` router only has PATCH). Excluding it
    means Django's own `View.dispatch()` routes a PUT request to
    `http_method_not_allowed()` (405) before `update()` (below) is ever
    reached — a stray PUT gets the correct "this verb doesn't exist"
    answer instead of being silently accepted, matching the frozen
    contract exactly rather than merely being a harmless no-op for it.
    `update()` still forces partial semantics (`partial=True`
    unconditionally) purely because `partial_update()` (PATCH) delegates
    into it — see that method's own docstring."""

    # Router-registered PUT is excluded so a stray full-replace request
    # 405s instead of silently landing on `update()` (see class docstring
    # above) — `packages/api-client/openapi.json` has no PUT operation for
    # this resource. `"head"`/`"options"` stay: DRF/Django handle both
    # generically and every other view in this block leaves them enabled
    # too.
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    # `.order_by(...)`: `Item` has no default `Meta.ordering` — an
    # unordered queryset paginates non-deterministically page-to-page
    # (DRF's own `UnorderedObjectListWarning`), which would make `GET
    # /items?page=2` an unreliable continuation of page 1. `created_at`
    # (insertion order) then `id` (a stable tiebreaker for same-instant
    # rows) gives every page a deterministic, repeatable order without
    # requiring a model-level change to core/models.py.
    queryset = Item.objects.all().order_by("created_at", "id")
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
        except (Item.DoesNotExist, ValueError, TypeError, DjangoValidationError):
            # ValueError/TypeError/DjangoValidationError: a malformed
            # (non-UUID) `item_id`. Which of these three Django's UUIDField
            # lookup actually raises for a value that isn't a well-formed
            # UUID depends on the value's shape — `django.core.exceptions.
            # ValidationError` (via `UUIDField.to_python()`, in the normal
            # `.get(pk=pk)` filtering path) is the common case, but
            # ValueError/TypeError are kept too since they're the cheaper,
            # narrower failure a raw `uuid.UUID(pk)` coercion elsewhere
            # could still raise. All three mean the same thing here: "not a
            # value that could ever address a real row." FastAPI's
            # path-typed `item_id: uuid.UUID` would instead reject that at
            # 422 (a routing-level type mismatch) before the handler ever
            # runs — a second, smaller accepted per-framework divergence
            # alongside the one this block's README already documents for
            # PageParams `extra="forbid"`. Treating it as "not found" here
            # (404) rather than "unvalidatable" (422) is the more
            # conservative of the two readings for an ID a caller already
            # has no way to have gotten right, and keeps this override's
            # error path single (one exception type raised, not two).
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

    @extend_schema(
        operation_id="health_check_health_get",
        tags=["health"],
        responses={200: HealthStatusSerializer},
    )
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

    @extend_schema(
        operation_id="readiness_check_readyz_get",
        tags=["health"],
        responses={200: ReadinessStatusSerializer, 503: ReadinessStatusSerializer},
    )
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


class RegisterView(APIView):
    """`POST /auth/register` (Stage 5b, #44) — real handler, the DRF
    counterpart to `app/api/routers/auth.py`'s `register`. Delegates
    straight to `AuthService.register` — raises `EmailAlreadyExists` (->
    409 `conflict`, via `core.exceptions.exception_handler`'s `AuthError`
    branch) for a duplicate normalized email, uncaught here (see this
    module's own docstring)."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(
        operation_id="register_auth_register_post",
        tags=["auth"],
        request=RegisterRequestSerializer,
        responses={201: PrincipalOutSerializer, 409: ErrorEnvelopeSerializer, 422: ErrorEnvelopeSerializer},
    )
    def post(self, request):
        serializer = RegisterRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        auth_service = build_auth_service()
        user = async_to_sync(auth_service.register)(
            serializer.validated_data["email"], serializer.validated_data["password"]
        )
        principal = PrincipalOutSerializer({"id": uuid.UUID(user.id), "email": user.email})
        return Response(principal.data, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    """`POST /auth/login` (Stage 5b, #44; verification + lockout + audit
    gate Stage 5c, #45) — real handler. Delegates to `AuthService.login`
    — raises `InvalidCredentials` (-> 401 `unauthenticated`) identically
    for an unknown email, a wrong password, an account locked out from
    too many recent failures, AND (as of Stage 5c) an account whose email
    isn't verified yet — all four are wire-BYTE-IDENTICAL, uncaught here
    (see that exception's own docstring on the deliberate
    user-enumeration defense, and `_core.AuthService.login`'s own
    docstring for the full 6-step state machine this now runs through
    `_build_login_auth_service()`'s wiring).

    Stage 5c: `auth_service` is now built via `_build_login_auth_service()`
    (this module, above) instead of the plain `build_auth_service()` every
    other `/auth/*` view still uses — the SAME `lockout`/
    `require_verification`/`events` wiring `backend/fastapi`'s
    `app/api/deps.py:get_auth_service` applies to its own `AuthService`."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(
        operation_id="login_auth_login_post",
        tags=["auth"],
        request=LoginRequestSerializer,
        responses={200: TokenResponseSerializer, 401: ErrorEnvelopeSerializer, 422: ErrorEnvelopeSerializer},
    )
    def post(self, request):
        serializer = LoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        auth_service = _build_login_auth_service()
        pair = async_to_sync(auth_service.login)(
            serializer.validated_data["email"], serializer.validated_data["password"]
        )
        tokens = TokenResponseSerializer({"access_token": pair.access, "refresh_token": pair.refresh})
        return Response(tokens.data)


class RefreshView(APIView):
    """`POST /auth/refresh` (Stage 5b, #44) — real handler. Delegates to
    `AuthService.refresh` — THE rotation-with-reuse-detection state
    machine (see `_core.py`'s own module docstring and
    `AuthService.refresh`'s docstring for the full state machine). Raises
    `InvalidToken` or `TokenReused` (both -> 401 `unauthenticated`,
    deliberately indistinguishable at the wire — see `TokenReused`'s own
    docstring and `core/exceptions.py`'s FIX-B section), uncaught here. A
    `TokenReused` raise has, as a side effect, ALREADY revoked the
    token's entire family in the DB by the time this handler's caller
    sees the 401."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(
        operation_id="refresh_auth_refresh_post",
        tags=["auth"],
        request=RefreshRequestSerializer,
        responses={200: TokenResponseSerializer, 401: ErrorEnvelopeSerializer, 422: ErrorEnvelopeSerializer},
    )
    def post(self, request):
        serializer = RefreshRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        auth_service = build_auth_service()
        pair = async_to_sync(auth_service.refresh)(serializer.validated_data["refresh_token"])
        tokens = TokenResponseSerializer({"access_token": pair.access, "refresh_token": pair.refresh})
        return Response(tokens.data)


class LogoutView(APIView):
    """`POST /auth/logout` (Stage 5b, #44) — real handler. Delegates to
    `AuthService.logout` — best-effort and idempotent by design (see that
    method's own docstring): an already-invalid, unknown, or
    already-revoked refresh token still returns 204, never an error.
    Revokes the entire token family, not just the presented token.
    Deliberately given no error `responses=` entry beyond 422 (see
    `app/api/routers/auth.py`'s identical, documented choice for its own
    `logout` route) — it's 204 and idempotent by design, never raises an
    error a client needs to handle."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(
        operation_id="logout_auth_logout_post",
        tags=["auth"],
        request=RefreshRequestSerializer,
        responses={204: None, 422: ErrorEnvelopeSerializer},
    )
    def post(self, request):
        serializer = RefreshRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        auth_service = build_auth_service()
        async_to_sync(auth_service.logout)(serializer.validated_data["refresh_token"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """`GET /auth/me` (Stage 5b, #44) — real handler, the bearer-scheme
    seam. `permission_classes = [AllowAny]`/`authentication_classes = []`
    stay unchanged from the Stage 4 stub — this view enforces
    authentication itself, via `resolve_principal` below, rather than
    through DRF's own `IsAuthenticated`/`authentication_classes` machinery
    (which would reject a missing/malformed bearer with DRF's own 403/401
    shape, bypassing this block's `ErrorEnvelope` — see
    `core/security/auth/django.py`'s `resolve_principal` docstring: a
    missing or malformed `Authorization` header raises `_core.InvalidToken`
    directly, the identical exception a present-but-invalid token raises,
    so both land on the SAME 401 `unauthenticated` envelope via
    `core/exceptions.py`'s `AuthError` branch).

    `resolve_principal` (async, bridged via `async_to_sync`) already
    verified the bearer access token and resolved it to `AccessClaims`
    before this method's body does anything else — a missing/malformed/
    expired token never reaches the `DjangoUserStore` lookup below at all.

    `AccessClaims` carries `sub` (the user id) and `roles`, but not
    `email` — this handler does one direct `DjangoUserStore.get_by_id`
    lookup to fill in `PrincipalOut.email`, independent of `AuthService`
    (which has no "fetch a profile" method — see `_core.py`'s `UserStore`
    Protocol; it's a storage seam for `AuthService`'s own register/login/
    refresh flows, not a general user-lookup API this view reaches for) —
    identical to `app/api/routers/auth.py`'s own `me` handler.

    The user having been deleted BETWEEN minting the access token and this
    request (a real, if narrow, race — access tokens are not individually
    revocable) is treated as `InvalidToken` (401), matching
    `AuthService.refresh`'s identical "row valid but the user it points to
    is gone" handling — NOT a 404, since the token itself is what's no
    longer trustworthy, not a missing resource the caller asked for by
    id.

    Stage 4 Step 4 (#27): the `HTTPBearer` security scheme is registered
    (`config/settings.py`'s `SPECTACULAR_SETTINGS["APPEND_COMPONENTS"]`)
    and this view opts into it via `@extend_schema(auth=[{"HTTPBearer":
    []}])` below (drf-spectacular's `auth` kwarg overrides `AutoSchema.
    get_auth()`, which is what actually populates the operation's
    `security` key) — an exact match with `openapi.json`'s own `security:
    [{"HTTPBearer": []}]` on this operation."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(
        operation_id="me_auth_me_get",
        tags=["auth"],
        responses={200: PrincipalOutSerializer, 401: ErrorEnvelopeSerializer},
        auth=[{"HTTPBearer": []}],
    )
    def get(self, request):
        auth_service = build_auth_service()
        claims = async_to_sync(resolve_principal)(request, auth_service)
        user = async_to_sync(DjangoUserStore().get_by_id)(claims.sub)
        if user is None:
            raise InvalidToken("This token no longer maps to an active user.")
        principal = PrincipalOutSerializer({"id": uuid.UUID(user.id), "email": user.email})
        return Response(principal.data)
