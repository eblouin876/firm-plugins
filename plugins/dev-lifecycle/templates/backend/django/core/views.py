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
from drf_spectacular.types import OpenApiTypes
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
    build_account_service,
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
    RequestPasswordResetRequestSerializer,
    ResetPasswordRequestSerializer,
    TokenResponseSerializer,
    VerifyEmailRequestSerializer,
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
    """`POST /auth/register` (Stage 5b, #44; account-lifecycle side effect
    Stage 5c, #45) — real handler, the DRF counterpart to `app/api/
    routers/auth.py`'s `register`. Delegates straight to `AuthService.
    register` — raises `EmailAlreadyExists` (-> 409 `conflict`, via
    `core.exceptions.exception_handler`'s `AuthError` branch) for a
    duplicate normalized email, uncaught here (see this module's own
    docstring).

    Stage 5c: on success, additionally (a) sends a verification email
    (`AccountService.request_email_verification(user)` — the freshly
    created `UserRecord` `AuthService.register` just returned, no extra
    lookup needed) and (b) emits an `auth.register` audit event. Neither
    changes this endpoint's response shape (still 201 `PrincipalOut`) —
    a project whose `settings.AUTH_REQUIRE_EMAIL_VERIFICATION` is `True`
    (the secure default) needs the caller to actually consume the emailed
    link (`POST /auth/verify-email`) before `LoginView`'s gated
    `AuthService.login` will let this account in.

    `request_email_verification` is wrapped in `try/except Exception` —
    the user row is already durably committed by the time this runs
    (`AuthService.register` returned successfully), so a verification-
    email failure here (SMTP outage, bounced address) must NEVER turn
    into a 500: the account already exists, a retry would just 409 on
    the duplicate email, `require_verification=True` means the account
    can't log in either way, and the wire caller (whoever showed the
    registration form) has no way to "undo" or recover a 500 here — it
    would brick a just-created account with no path forward. Register
    stays 201 regardless of whether the email actually went out; the
    failure is only logged/audited (`auth.register.
    verification_email_failed`, no PII/token in the event), never
    surfaced to the caller. The recovery path for an account whose
    verification email never arrived is `POST /auth/request-password-
    reset` -> `POST /auth/reset-password` — `AccountService.
    reset_password` also marks the email verified (see that method's own
    docstring, `_core.py`), so a user who never got their verification
    link can still get into their account. Byte-for-byte the same
    rationale as `app/api/routers/auth.py`'s own `register` handler
    (adversarial-review fix M2 there)."""

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
        account_service = build_account_service()
        try:
            async_to_sync(account_service.request_email_verification)(user)
        except Exception:
            # M2 (ported from app/api/routers/auth.py's register handler):
            # never let a verification-email delivery failure 500 an
            # already-committed registration -- see this view's own
            # docstring above. No PII/token in this event -- just that it
            # happened, for a human to notice and, if needed, resend by
            # hand.
            async_to_sync(AuditAuthEventSink().emit)(
                "auth.register.verification_email_failed", actor=user.id, outcome="failure"
            )
        async_to_sync(AuditAuthEventSink().emit)("auth.register", actor=user.id, outcome="success")
        principal = PrincipalOutSerializer({"id": uuid.UUID(user.id), "email": user.email})
        return Response(principal.data, status=status.HTTP_201_CREATED)


class VerifyEmailView(APIView):
    """`POST /auth/verify-email` (Stage 5c, #45) — real handler, the DRF
    counterpart to `app/api/routers/auth.py`'s `verify_email`. Delegates
    to `AccountService.verify_email` — raises `InvalidSingleUseToken`
    (-> 401 `unauthenticated`, generic and wire-identical to every other
    single-use-token rejection reason — see that exception's own
    docstring) for an unknown/expired/already-used/wrong-purpose token,
    uncaught here (see this module's own docstring). On success, marks
    the token's owning user's email verified — see `LoginView`'s
    `require_verification` gate (`_build_login_auth_service`, above) for
    why that matters: with `settings.AUTH_REQUIRE_EMAIL_VERIFICATION=True`
    (the default), login for this account was refused (generically, as
    `InvalidCredentials`) until this endpoint succeeds."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(
        operation_id="verify_email_auth_verify_email_post",
        tags=["auth"],
        request=VerifyEmailRequestSerializer,
        responses={204: None, 401: ErrorEnvelopeSerializer, 422: ErrorEnvelopeSerializer},
    )
    def post(self, request):
        serializer = VerifyEmailRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account_service = build_account_service()
        async_to_sync(account_service.verify_email)(serializer.validated_data["token"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class RequestPasswordResetView(APIView):
    """`POST /auth/request-password-reset` (Stage 5c, #45) — real handler,
    the DRF counterpart to `app/api/routers/auth.py`'s
    `request_password_reset`. Delegates to `AccountService.
    request_password_reset` — that method NEVER raises and never reveals
    whether `email` has an account (see its own docstring on the anti-
    user-enumeration defense this mirrors from `AuthService.login`'s own
    `InvalidCredentials`), so this view ALWAYS returns 202 with a
    genuinely EMPTY body (`Response(status=202)` with no data — DRF
    sends no content body at all when a view returns no `data`, matching
    `app/api/routers/auth.py`'s own explicit `Response(..., content=b"")`
    — a byte-identical, content-free response is the strongest form of
    "this endpoint reveals nothing" for a known email and an unknown one
    alike), never a 404/409 that would leak account existence. A `422`
    (declared below) is the one response shape this endpoint CAN still
    send, for a request body that fails `RequestPasswordResetRequestSerializer`'s
    own schema validation (e.g. an empty `email` string) before this
    view's body ever runs."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(
        operation_id="request_password_reset_auth_request_password_reset_post",
        tags=["auth"],
        request=RequestPasswordResetRequestSerializer,
        # `202: OpenApiTypes.ANY` (`build_basic_type(OpenApiTypes.ANY) ==
        # {}`), not `None` -- matches `packages/api-client/openapi.json`'s
        # own documented 202 exactly: FastAPI's `Response(status_code=202,
        # content=b"")` (no `response_model`) still documents a
        # `application/json` media type with an empty (`{}`, "unspecified
        # shape") schema, NOT an absent `content` key the way a genuinely
        # bodiless `None` response (`LogoutView`'s 204, below) does. A raw
        # `{}` dict here is NOT equivalent -- `drf_spectacular.openapi.
        # AutoSchema._get_response_for_code`'s `if not serializer:` falsy
        # check fires for an empty dict BEFORE its `isinstance(serializer,
        # dict)` raw-schema branch is ever reached, collapsing it to "No
        # response body" (no `content` key at all) instead -- `OpenApiTypes.
        # ANY` is `is_basic_type`, so it reaches `build_basic_type` instead,
        # which is what actually produces the `{}` schema this needs. See
        # tests/test_schema_conformance.py's strict wire-surface proof,
        # which this documents.
        responses={202: OpenApiTypes.ANY, 422: ErrorEnvelopeSerializer},
    )
    def post(self, request):
        serializer = RequestPasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account_service = build_account_service()
        async_to_sync(account_service.request_password_reset)(serializer.validated_data["email"])
        return Response(status=status.HTTP_202_ACCEPTED)


class ResetPasswordView(APIView):
    """`POST /auth/reset-password` (Stage 5c, #45) — real handler, the DRF
    counterpart to `app/api/routers/auth.py`'s `reset_password`.
    Delegates to `AccountService.reset_password` — raises
    `InvalidSingleUseToken` (-> 401 `unauthenticated`, generic — see
    `VerifyEmailView`'s docstring above for the identical rationale) for
    an unknown/expired/already-used/wrong-purpose reset token, uncaught
    here. On success, revokes EVERY refresh-token family the user has
    (every device/session is logged out, not just the one that requested
    the reset — see `AccountService.reset_password`'s own docstring,
    `_core.py`) and, if a lockout policy is wired, lifts any failed-login
    lockout on the account — the same underlying `DjangoLockoutStore`
    table `LoginView`'s own `_build_login_auth_service()` records
    against, so the reset account can log in with its new password
    immediately."""

    permission_classes = [AllowAny]
    authentication_classes: list = []

    @extend_schema(
        operation_id="reset_password_auth_reset_password_post",
        tags=["auth"],
        request=ResetPasswordRequestSerializer,
        responses={204: None, 401: ErrorEnvelopeSerializer, 422: ErrorEnvelopeSerializer},
    )
    def post(self, request):
        serializer = ResetPasswordRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account_service = build_account_service()
        async_to_sync(account_service.reset_password)(
            serializer.validated_data["token"], serializer.validated_data["new_password"]
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


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
