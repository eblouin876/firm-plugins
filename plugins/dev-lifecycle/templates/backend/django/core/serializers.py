"""Request/response serializers for this block's DRF contract-emission
layer (Stage 4 Step 2, #27) — the DRF counterpart to backend/fastapi's
`app/schemas/{item,auth,health}.py`. Field names/types/required-ness are
kept in exact step with `packages/api-client/openapi.json`'s `ItemOut`/
`ItemCreate`/`ItemUpdate`/... schemas (see this block's README,
"Conformance") — `core/views.py` is what actually renders these over HTTP,
this module only owns the shape."""

from __future__ import annotations

from rest_framework import serializers

from core.contract.errors import ErrorCode
from core.models import Item


class ItemOutSerializer(serializers.ModelSerializer):
    """The read shape — matches `openapi.json`'s `ItemOut` exactly: `id`,
    `name`, `description`, `created_at`, `updated_at`. Deliberately NOT
    `deleted_at`, even though the model carries it for soft-delete
    bookkeeping (core/models.py) — every field here is output-only
    (`read_only_fields = fields`); this serializer is never constructed
    with `data=...`, only `ItemOutSerializer(instance)`.

    `name`/`description` explicit `max_length` (Stage 4 Step 4, #27,
    schema-conformance fix round): a PLAIN `ModelSerializer`-derived
    read-only field carries no `MaxLengthValidator` (DRF doesn't attach
    validators to fields it will never validate incoming data against),
    so drf-spectacular's generated schema silently dropped the
    `maxLength` constraint `openapi.json`'s own `ItemOut` documents on
    these same two fields (pydantic's `ItemOut` reuses `ItemBase`'s
    `Field(max_length=...)` regardless of read/write direction) —
    documentation-only, zero effect on runtime behavior (still never
    validated, since both fields stay `read_only=True`); this exists
    purely to close that generated-schema gap,
    `tests/test_schema_conformance.py`'s wire-surface proof."""

    name = serializers.CharField(max_length=200, min_length=1, read_only=True)
    description = serializers.CharField(max_length=2000, allow_null=True, read_only=True)

    class Meta:
        model = Item
        fields = ["id", "name", "description", "created_at", "updated_at"]
        read_only_fields = fields


class ItemCreateSerializer(serializers.ModelSerializer):
    """The create-body shape — matches `openapi.json`'s `ItemCreate`:
    `name` required, explicit `min_length=1`/`allow_blank=False` (matches
    the frozen contract's `minLength: 1` — `allow_blank=False` alone would
    give the same practical rejection for `name=""`, but the explicit
    `min_length=1` documents the wire constraint directly rather than
    leaning on that DRF default). `description` optional AND nullable —
    `default=None` (not just `required=False`) so a client that omits it
    entirely still lands `description=None` in `validated_data`, matching
    `ItemBase.description: str | None = Field(default=None, ...)`'s own
    "omitted means None" default on the FastAPI side (`core/views.py`'s
    `ItemViewSet.create` passes `validated_data` straight to
    `Item.objects.create(**...)`; without this default, Django's own
    `CharField.get_default()` would silently store `""` instead of `NULL`
    for an omitted field)."""

    name = serializers.CharField(min_length=1, max_length=200, allow_blank=False)
    description = serializers.CharField(
        max_length=2000, required=False, allow_null=True, allow_blank=True, default=None
    )

    class Meta:
        model = Item
        fields = ["name", "description"]


class ItemUpdateSerializer(serializers.ModelSerializer):
    """The update-body (PATCH) shape — matches `openapi.json`'s
    `ItemUpdate`: every field optional, so a client can PATCH a subset.
    Deliberately NO `default=` on either field (unlike `ItemCreateSerializer`
    above) — DRF only adds a key to `validated_data` for a field the
    client actually sent (explicit value, including an explicit
    `"description": null`) when `required=False` carries no default; an
    omitted field is left out of `validated_data` entirely. That mirrors
    FastAPI's `payload.model_dump(exclude_unset=True)` (app/api/routers/
    items.py's `update_item`) field-for-field: only explicitly-set fields
    land on the existing row (`core/views.py`'s `ItemViewSet.update`)."""

    name = serializers.CharField(min_length=1, max_length=200, allow_blank=False, required=False)
    description = serializers.CharField(max_length=2000, required=False, allow_null=True, allow_blank=True)

    class Meta:
        model = Item
        fields = ["name", "description"]


class HealthStatusSerializer(serializers.Serializer):
    """Matches `openapi.json`'s `HealthStatus`: `{"status": "..."}`."""

    status = serializers.CharField()


class ReadinessStatusSerializer(serializers.Serializer):
    """Matches `openapi.json`'s `ReadinessStatus`: `{"status": "..."}`."""

    status = serializers.CharField()


class RegisterRequestSerializer(serializers.Serializer):
    """Stage 5b (#44) `POST /auth/register` request shape — matches
    `openapi.json`'s `RegisterRequest` exactly: `email`/`password`, each
    `min_length=1`, both required. Same strictness posture as
    `LoginRequestSerializer` immediately below (a plain `Serializer`, not
    `ModelSerializer` — this never round-trips straight to `core.models.
    User`, `core.security.auth.stores.DjangoUserStore.create` owns that
    mapping, including the Argon2id hash `AuthService.register` computes
    from `password` before any DB write)."""

    email = serializers.CharField(min_length=1)
    password = serializers.CharField(min_length=1)


class LoginRequestSerializer(serializers.Serializer):
    """`POST /auth/login` request shape — matches `openapi.json`'s
    `LoginRequest`. Defined alongside backend/fastapi's `app/schemas/
    auth.py`, so the wire contract (and the `HTTPBearer` security scheme
    a real OpenAPI schema view documents) is locked in identically on
    both tracks."""

    email = serializers.CharField(min_length=1)
    password = serializers.CharField(min_length=1)


class RefreshRequestSerializer(serializers.Serializer):
    """Matches `openapi.json`'s `RefreshRequest`. See `LoginRequestSerializer`."""

    refresh_token = serializers.CharField(min_length=1)


class TokenResponseSerializer(serializers.Serializer):
    """Matches `openapi.json`'s `TokenResponse`. Documentation-only as of
    this step — every `/auth/*` handler returns the plain `{"detail": ...}`
    501-stub body instead (`core/views.py`'s module docstring), never this
    shape; Stage 5 is what actually returns it."""

    access_token = serializers.CharField()
    refresh_token = serializers.CharField()
    token_type = serializers.CharField(default="bearer")


class PrincipalOutSerializer(serializers.Serializer):
    """Matches `openapi.json`'s `PrincipalOut`. See `TokenResponseSerializer`."""

    id = serializers.UUIDField()
    email = serializers.CharField()


# ---------------------------------------------------------------------------
# Documentation-only: the ErrorEnvelope shape, for drf-spectacular
# (Stage 4 Step 4, #27). `core.exceptions.exception_handler` builds every
# actual error response straight from `core.contract.errors.ErrorEnvelope`
# (the vendored Pydantic model) — it never constructs or validates against
# these DRF serializers, which exist ONLY so `core/views.py`'s
# `@extend_schema(responses={...: ErrorEnvelopeSerializer})` declarations
# have a DRF serializer to point the schema generator at (drf-spectacular
# documents DRF serializers, not arbitrary Pydantic models). Field-for-field
# copies of `core.contract.errors.{ErrorDetail,ErrorBody,ErrorEnvelope}` —
# kept in sync by hand since there are only three, small, rarely-changing
# fields; a drift here would only ever affect the DOCUMENTED schema, never
# the actual wire response (which is exactly what the wire-surface
# conformance proof, tests/test_schema_conformance.py, is there to catch).
# Class names deliberately end in `Serializer` so drf-spectacular's default
# naming (strips that suffix) produces component names `ErrorDetail`/
# `ErrorBody`/`ErrorEnvelope` — an exact match with `openapi.json`'s own
# component names, not a coincidence.
# ---------------------------------------------------------------------------


class ErrorDetailSerializer(serializers.Serializer):
    """Matches `openapi.json`'s `ErrorDetail`: one item in an error's
    optional `details` list."""

    field = serializers.CharField(required=False, allow_null=True, default=None)
    message = serializers.CharField()


class ErrorBodySerializer(serializers.Serializer):
    """Matches `openapi.json`'s `ErrorBody`. `code` is a `ChoiceField` over
    `core.contract.errors.ErrorCode`'s own members — the same closed,
    versioned set — so the generated schema documents a proper enum, not an
    unconstrained string, matching `openapi.json`'s own `ErrorCode` enum
    component."""

    code = serializers.ChoiceField(choices=[member.value for member in ErrorCode])
    message = serializers.CharField()
    details = ErrorDetailSerializer(many=True, required=False, allow_null=True, default=None)


class ErrorEnvelopeSerializer(serializers.Serializer):
    """Matches `openapi.json`'s `ErrorEnvelope` — THE error shape every
    non-2xx response in this block uses except the one documented exception
    (429 rate-limit denial's plain `{"detail": ...}` — see README.md,
    "Conformance")."""

    error = ErrorBodySerializer()
