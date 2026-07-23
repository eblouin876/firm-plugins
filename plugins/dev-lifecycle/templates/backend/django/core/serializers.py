"""Request/response serializers for this block's DRF contract-emission
layer (Stage 4 Step 2, #27) — the DRF counterpart to backend/fastapi's
`app/schemas/{item,auth,health}.py`. Field names/types/required-ness are
kept in exact step with `packages/api-client/openapi.json`'s `ItemOut`/
`ItemCreate`/`ItemUpdate`/... schemas (see this block's README,
"Conformance") — `core/views.py` is what actually renders these over HTTP,
this module only owns the shape."""

from __future__ import annotations

from rest_framework import serializers

from core.models import Item


class ItemOutSerializer(serializers.ModelSerializer):
    """The read shape — matches `openapi.json`'s `ItemOut` exactly: `id`,
    `name`, `description`, `created_at`, `updated_at`. Deliberately NOT
    `deleted_at`, even though the model carries it for soft-delete
    bookkeeping (core/models.py) — every field here is output-only
    (`read_only_fields = fields`); this serializer is never constructed
    with `data=...`, only `ItemOutSerializer(instance)`."""

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


class LoginRequestSerializer(serializers.Serializer):
    """Stage 5 (#28) auth-stub request shape — matches `openapi.json`'s
    `LoginRequest`. Defined now, like backend/fastapi's `app/schemas/
    auth.py`, so the wire contract (and the `HTTPBearer` security scheme
    a real OpenAPI schema view documents in a later step) is locked in
    even though every `/auth/*` handler (`core/views.py`) is a plain 501
    stub until Stage 5 implements it for real."""

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
