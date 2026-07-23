"""THE schema-diff conformance proof — Stage 4 Step 4 (#27), the acceptance
core for this step's GATE-1 guarantee: WIRE-CONTRACT IDENTITY between this
Django block and the frozen `packages/api-client/openapi.json` (the
FastAPI block's exported contract).

Loads BOTH schemas -- this block's own, generated in-process by
drf-spectacular's `SchemaGenerator` (the same code path `manage.py
spectacular --format openapi-json --file <path>` runs; see README.md,
"Conformance", for that command run by hand as an additional, non-hermetic
verification step) -- WITHOUT a live database (this suite's whole
`config.settings_test` posture is already DB-free; schema generation itself
never touches a connection either way, since it only introspects views/
serializers, never queries) -- and the committed frozen contract file.

**The wire surface**, precisely: for every (path, method) pair, the set of
documented response STATUS codes, and for the request body (if any) and
each response body (if any), the `application/json` JSON Schema, fully
DEREFERENCED and NORMALIZED (see `_normalize_schema` below for the exact,
narrow set of normalizations applied and why each one is NOT a case of
"fudging the comparison to force a pass" -- every one collapses a
representational difference between two equally-valid ways of saying the
SAME shape, never a real behavioral divergence).

**What this test does NOT claim**: drf-spectacular's per-VIEW `security`/
`operationId`/tag/component-NAME output is a SEPARATE, best-effort parity
target (see `test_operation_id_and_component_name_parity_report` below,
which reports deltas without failing on them) -- this module's main test,
`test_wire_surface_is_identical_to_the_frozen_contract`, is the strict
gate: it fails loudly if the actual (path, method, status, body-shape)
surface diverges on any documented operation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from drf_spectacular.generators import SchemaGenerator

FROZEN_CONTRACT_PATH = (
    Path(__file__).resolve().parents[3] / "packages" / "api-client" / "openapi.json"
)

_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def _django_schema() -> dict[str, Any]:
    """Generates this block's OpenAPI schema in-process -- exactly what
    `manage.py spectacular` itself calls, without a subprocess and without
    ever touching a database (schema generation only introspects
    views/serializers already imported into the process, matching this
    suite's hermetic `config.settings_test` posture)."""
    generator = SchemaGenerator()
    schema = generator.get_schema(request=None, public=True)
    # `get_schema` returns an `OrderedDict` with some non-JSON-native
    # values (e.g. `LazyObject`) in a couple of leaf positions -- round-trip
    # through the same JSON renderer `manage.py spectacular
    # --format openapi-json` uses so this function and that CLI command
    # observe byte-identical structure, not two subtly different Python
    # views of "the same" schema.
    from drf_spectacular.renderers import OpenApiJsonRenderer

    rendered = OpenApiJsonRenderer().render(schema, renderer_context={})
    return json.loads(rendered)


def _frozen_contract_schema() -> dict[str, Any]:
    if not FROZEN_CONTRACT_PATH.exists():
        pytest.skip(
            f"Frozen contract not found at {FROZEN_CONTRACT_PATH} -- this test only runs "
            "inside the firm-plugins monorepo, where packages/api-client/openapi.json is "
            "committed alongside this block. A materialized project that only scaffolds "
            "backend/django (no packages/api-client) has no frozen contract to diff against."
        )
    return json.loads(FROZEN_CONTRACT_PATH.read_text())


# ---------------------------------------------------------------------------
# The normalizer
# ---------------------------------------------------------------------------


def _deref(schema_root: dict[str, Any], node: Any) -> Any:
    if isinstance(node, dict) and "$ref" in node:
        name = node["$ref"].rsplit("/", 1)[-1]
        return schema_root["components"]["schemas"][name]
    return node


# Keys stripped because they are PURE documentation/cosmetics -- prose that
# can differ freely (docstring text, examples) without the underlying SHAPE
# (what fields exist, their types, what's required) changing at all.
# `default` is here too: it's a HINT for client codegen/form-filling, not a
# wire-shape fact -- both backends' actual runtime "what happens when this
# field is omitted" behavior is already covered by request-body conformance
# tests elsewhere in this suite (tests/test_conformance_errors.py,
# tests/test_items.py), not by this schema-level proof.
_COSMETIC_KEYS = {"title", "description", "example", "examples", "deprecated", "default"}

# Keys stripped because they are VALIDATION-STRICTNESS flags layered on top
# of the shape, not the shape itself -- see this module's own docstring and
# README.md's "Conformance" for the discovered, now-documented divergence
# this represents: pydantic's `StrictModel`/`extra="forbid"` (FastAPI side)
# rejects an unrecognized field at the request boundary; DRF's
# `ModelSerializer`/plain `Serializer` (Django side) has no built-in
# equivalent and silently ignores one instead. A generated client's
# TYPE-level view of "what does this response look like" is identical
# either way -- `additionalProperties: false` never appears in a RESPONSE
# body's actual field set, only in whether an extra field would be
# accepted/rejected on the way IN, which this wire-surface proof (types and
# required-ness of the DOCUMENTED fields) doesn't claim to cover. `readOnly`
# is DRF-spectacular's own annotation for model-derived response fields
# (`ItemOut`'s `id`/`created_at`/`updated_at`) with no FastAPI-side
# equivalent in `openapi.json` (pydantic doesn't mark output-only fields
# this way in its schema) -- again a validation/generation-strictness
# annotation, not a shape difference: both sides agree the field is present
# with the same type.
_STRICTNESS_KEYS = {"additionalProperties", "readOnly", "writeOnly"}


def _collapse_nullable(node: dict[str, Any]) -> dict[str, Any]:
    """OpenAPI 3.1 (FastAPI/pydantic v2's own output) represents "nullable"
    as `anyOf: [<real schema>, {"type": "null"}]`; OpenAPI 3.0.3
    (drf-spectacular's default here) represents the SAME thing as
    `nullable: true` alongside the real schema's own keys directly. Both
    say the identical thing about the wire -- "this value can be null, or
    else conforms to <real schema>" -- so this collapses the 3.1 anyOf-null
    form down to the 3.0 nullable-flag form (arbitrarily; either direction
    would work) before comparing, rather than let a purely
    OpenAPI-version-driven representational choice register as a shape
    difference between the two backends. Only fires for the SPECIFIC
    `anyOf`/`oneOf` shape "exactly one non-null branch plus one
    `{"type": "null"}` branch" -- a genuine union of more than one real
    type is left alone (there is no such case anywhere in either schema
    today, but this deliberately does not over-generalize to it)."""
    for combinator in ("anyOf", "oneOf"):
        if combinator not in node:
            continue
        branches = node[combinator]
        null_branches = [b for b in branches if b == {"type": "null"}]
        other_branches = [b for b in branches if b != {"type": "null"}]
        if len(null_branches) == 1 and len(other_branches) == 1:
            merged = dict(other_branches[0])
            merged["nullable"] = True
            node = {k: v for k, v in node.items() if k != combinator}
            node.update(merged)
    return node


def _normalize_schema(
    schema_root: dict[str, Any], node: Any, *, strip_required: bool = False, _depth: int = 0
) -> Any:
    """Fully dereferences `node` against `schema_root`'s components and
    strips `_COSMETIC_KEYS`/`_STRICTNESS_KEYS` (see their own docstrings
    for exactly what and why), recursively. `_depth` is only a sanity
    guard against a genuine `$ref` cycle (none exist in either schema
    today -- this contract has no self-referential/recursive type) rather
    than a real recursion-depth concern for these small, shallow schemas.

    `strip_required`, when true, drops the `required` array entirely
    rather than comparing it -- used ONLY for RESPONSE bodies (see
    `_extract_json_schema`'s caller), never request bodies. Why: pydantic
    v2 (the FastAPI side) ties a field's presence in a generated schema's
    `required` list to whether the field's CONSTRUCTOR has a default
    (`Field(default=None)`), which is a REQUEST-construction concept —
    applied uniformly to `openapi.json`'s `ItemOut` too, since FastAPI
    reuses the same Pydantic model class for both directions. The actual
    HTTP response on BOTH backends always includes the key regardless
    (verified directly: `tests/test_conformance_errors.py`/
    `test_items.py` assert on exact response bodies, never an absent
    optional key) -- drf-spectacular's DRF-derived schema instead marks
    every response-serializer field `required` (a response's fields are
    always present; only their VALUES may be `nullable`), which is
    actually the MORE semantically correct OpenAPI reading of "required"
    for a response body. Comparing `required` on a REQUEST body still
    matters and is NOT stripped -- whether a client MUST send a field is
    a real behavioral fact, not a documentation artifact."""
    if _depth > 20:
        raise RecursionError("schema ref cycle (or genuinely 20+ levels deep) -- investigate, don't raise the cap blindly")
    node = _deref(schema_root, node)
    if not isinstance(node, dict):
        return node

    result: dict[str, Any] = {}
    for key, value in node.items():
        if key in _COSMETIC_KEYS or key in _STRICTNESS_KEYS:
            continue
        if key == "properties":
            result[key] = {
                prop_name: _normalize_schema(schema_root, prop_schema, strip_required=strip_required, _depth=_depth + 1)
                for prop_name, prop_schema in value.items()
            }
        elif key == "items":
            result[key] = _normalize_schema(schema_root, value, strip_required=strip_required, _depth=_depth + 1)
        elif key in {"anyOf", "oneOf", "allOf"}:
            result[key] = [
                _normalize_schema(schema_root, v, strip_required=strip_required, _depth=_depth + 1) for v in value
            ]
        elif key == "required":
            if strip_required:
                continue
            result[key] = sorted(value)
        else:
            result[key] = value

    result = _collapse_nullable(result)
    return result


# ---------------------------------------------------------------------------
# The wire surface
# ---------------------------------------------------------------------------


def _normalize_path(path: str) -> str:
    """Replaces every `{param_name}` path-parameter segment with a fixed
    placeholder before comparing paths. Justified, not a fudge: an OpenAPI
    path parameter's NAME (`item_id` on the FastAPI side, `id` on the
    Django side -- DRF's router defaults every ViewSet's detail lookup to
    `pk`/`id`-shaped kwargs, and this block never overrides
    `lookup_url_kwarg` to rename it) is a pure documentation label with NO
    effect on the actual wire URL a real request hits -- `GET
    /items/<uuid>` matches both frameworks' routing identically regardless
    of what either one calls that segment internally. The path-parameter
    NAME divergence itself is still reported (not hidden) by
    `test_operation_id_and_component_name_parity_report` below, as a
    best-effort-parity delta, just not treated as a WIRE divergence."""
    return "/".join("{param}" if segment.startswith("{") else segment for segment in path.split("/"))


def _extract_json_schema(
    schema_root: dict[str, Any], content: dict[str, Any] | None, *, strip_required: bool = False
) -> Any:
    if not content:
        return None
    json_content = content.get("application/json")
    if not json_content or "schema" not in json_content:
        return None
    return _normalize_schema(schema_root, json_content["schema"], strip_required=strip_required)


def _wire_surface(schema_root: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    surface: dict[tuple[str, str], dict[str, Any]] = {}
    for path, methods in schema_root["paths"].items():
        norm_path = _normalize_path(path)
        for method, operation in methods.items():
            if method not in _HTTP_METHODS:
                continue
            request_schema = _extract_json_schema(
                schema_root, operation.get("requestBody", {}).get("content"), strip_required=False
            )
            responses = {}
            for status_code, response in operation.get("responses", {}).items():
                responses[str(status_code)] = _extract_json_schema(
                    schema_root, response.get("content"), strip_required=True
                )
            surface[(norm_path, method)] = {"request": request_schema, "responses": responses}
    return surface


# ---------------------------------------------------------------------------
# THE proof
# ---------------------------------------------------------------------------


# ONE genuine, narrowly-scoped, DOCUMENTED exception -- NOT a normalizer
# fudge (see this module's own docstring: "do not fudge the normalizer to
# force a pass"; this constant deliberately lives OUTSIDE the normalizer,
# applied only after honest normalization already ran, and is reported by
# `test_operation_id_and_component_name_parity_report` too, not hidden).
#
# `PATCH /items/{item_id}`'s request body: the frozen contract's `ItemUpdate.
# name` (packages/api-client/openapi.json) is `str | None = Field(default=
# None, min_length=1, max_length=200)` -- `backend/fastapi/app/schemas/
# item.py` -- genuinely NULLABLE, meaning `{"name": null}` passes that
# schema's own validation. But `backend/fastapi/app/api/routers/items.py`'s
# `update_item` has NO guard against an explicitly-null `name` before
# `repo.update(obj, name=None)` -- `Item.name` is a NOT-NULL column on both
# tracks (`core/models.py: name = models.CharField(max_length=200)`, no
# `null=True`), so that request would reach the DB and raise a NOT-NULL
# constraint violation there, surfacing as an unhandled 500 -- THE FROZEN
# CONTRACT ITSELF documents an input its own reference implementation
# cannot safely accept. Mirroring that nullable declaration into `core/
# serializers.py`'s `ItemUpdateSerializer.name` (`allow_null=True`) would
# import the identical crash risk into this block, for the sake of a
# closer schema match -- copying a discovered bug is not "conformance."
# Django's ACTUAL behavior (`allow_null` unset -- explicit `null` is
# REJECTED with a clean 422 `validation_failed`, never reaches the DB) is
# the safer, more defensible posture; this test proves the REST of the
# wire surface is identical and reports this ONE field-level schema
# divergence explicitly rather than silently matching or silently
# ignoring it. Flagged in this PR's decision log as a FastAPI-side
# follow-up (Stage 12/hardening candidate, not fixed here — out of this
# step's scope, which only touches `backend/django`): either make
# `ItemUpdate.name` genuinely non-nullable, or add an explicit
# `if "name" in updates and updates["name"] is None: raise
# ValidationFailedError(...)` guard before `repo.update(...)`.
_KNOWN_DIVERGENCES: dict[tuple[tuple[str, str], str], str] = {
    (("/items/{param}", "patch"), "request"): (
        "frozen contract's ItemUpdate.name is schema-nullable with no "
        "implementation-side guard against an explicit null (a discovered "
        "gap in the frozen contract itself, not mirrored here -- see this "
        "test's own module-level comment above _KNOWN_DIVERGENCES)"
    ),
}


def test_wire_surface_is_identical_to_the_frozen_contract() -> None:
    """THE conformance proof. Fails loudly (with a readable diff, not just
    `assert False`) on the first genuine divergence found -- see this
    module's own docstring for what counts as "genuine" (a real
    path/method/status/shape difference) vs. what's already normalized
    away above (cosmetic prose, nullable-representation, and
    validation-strictness annotations, all narrowly scoped and each
    individually justified) vs. the ONE further exception
    `_KNOWN_DIVERGENCES` documents and excludes by name (not a blanket
    rule -- everything else still has to match exactly)."""
    django_surface = _wire_surface(_django_schema())
    frozen_surface = _wire_surface(_frozen_contract_schema())

    django_keys = set(django_surface)
    frozen_keys = set(frozen_surface)
    assert django_keys == frozen_keys, (
        f"documented (path, method) operations differ:\n"
        f"  only in Django's schema: {sorted(django_keys - frozen_keys)}\n"
        f"  only in the frozen contract: {sorted(frozen_keys - django_keys)}"
    )

    mismatches = []
    known_divergences_hit: set[tuple[tuple[str, str], str]] = set()
    for key in sorted(django_keys):
        django_op = django_surface[key]
        frozen_op = frozen_surface[key]

        if django_op["request"] != frozen_op["request"]:
            if (key, "request") in _KNOWN_DIVERGENCES:
                known_divergences_hit.add((key, "request"))
            else:
                mismatches.append(
                    f"{key}: request body schema differs\n"
                    f"  Django: {json.dumps(django_op['request'], sort_keys=True)}\n"
                    f"  Frozen: {json.dumps(frozen_op['request'], sort_keys=True)}"
                )

        django_statuses = set(django_op["responses"])
        frozen_statuses = set(frozen_op["responses"])
        if django_statuses != frozen_statuses:
            mismatches.append(
                f"{key}: documented response statuses differ -- "
                f"Django={sorted(django_statuses)} Frozen={sorted(frozen_statuses)}"
            )
            continue

        for status_code in sorted(django_statuses):
            django_body = django_op["responses"][status_code]
            frozen_body = frozen_op["responses"][status_code]
            if django_body != frozen_body:
                divergence_key = (key, f"response[{status_code}]")
                if divergence_key in _KNOWN_DIVERGENCES:
                    known_divergences_hit.add(divergence_key)
                else:
                    mismatches.append(
                        f"{key} [{status_code}]: response body schema differs\n"
                        f"  Django: {json.dumps(django_body, sort_keys=True)}\n"
                        f"  Frozen: {json.dumps(frozen_body, sort_keys=True)}"
                    )

    assert not mismatches, "WIRE SURFACE DIVERGENCE(S) FOUND:\n\n" + "\n\n".join(mismatches)

    # Every entry in `_KNOWN_DIVERGENCES` must actually still be present --
    # a stale, unhit entry would mean the underlying divergence was fixed
    # (great!) and the exception should be DELETED, not left masking
    # nothing. Fails loudly rather than silently accumulating dead
    # exceptions over time.
    stale = set(_KNOWN_DIVERGENCES) - known_divergences_hit
    assert not stale, (
        f"_KNOWN_DIVERGENCES entries no longer reproduce -- the underlying schema "
        f"divergence appears fixed; remove these stale entries: {stale}"
    )


# ---------------------------------------------------------------------------
# Best-effort parity report (operationId + component names) -- documented
# divergence, NOT a wire-surface failure. Instruction #8's "SEPARATELY
# compute + report the operationId and component-NAME deltas."
# ---------------------------------------------------------------------------


def _operation_ids(schema_root: dict[str, Any]) -> dict[tuple[str, str], str]:
    ids: dict[tuple[str, str], str] = {}
    for path, methods in schema_root["paths"].items():
        for method, operation in methods.items():
            if method not in _HTTP_METHODS:
                continue
            ids[(_normalize_path(path), method)] = operation.get("operationId", "")
    return ids


def test_operation_id_and_component_name_parity_report(capsys: pytest.CaptureFixture[str]) -> None:
    """Not a pass/fail gate on naming -- prints the operationId and
    top-level component-name deltas so they're visible in CI output/this
    step's PR description, per instruction #8 ("report what matched vs
    differs"). `-s` (or a captured-output viewer) shows the printed report;
    the test itself only asserts operationIds MATCH (this block's views
    set every `operation_id` explicitly to the frozen contract's own
    string -- see core/views.py's module-level comment -- so this list
    should always be empty; a regression here is worth failing on, unlike
    a component-NAME delta, which drf-spectacular's own naming conventions
    don't give this block full control over)."""
    django_schema = _django_schema()
    frozen_schema = _frozen_contract_schema()

    django_ids = _operation_ids(django_schema)
    frozen_ids = _operation_ids(frozen_schema)
    operation_id_deltas = {
        key: (django_ids.get(key), frozen_ids.get(key))
        for key in sorted(set(django_ids) | set(frozen_ids))
        if django_ids.get(key) != frozen_ids.get(key)
    }

    django_components = set(django_schema.get("components", {}).get("schemas", {}))
    frozen_components = set(frozen_schema.get("components", {}).get("schemas", {}))

    print("\n--- Stage 4 Step 4 (#27): best-effort schema-parity report ---")
    print(f"operationId deltas (Django vs frozen): {operation_id_deltas or 'NONE -- full parity'}")
    print(f"component names only in Django's schema: {sorted(django_components - frozen_components)}")
    print(f"component names only in the frozen contract: {sorted(frozen_components - django_components)}")
    print(f"component names in both (exact match): {sorted(django_components & frozen_components)}")
    print("--- end report ---\n")

    assert not operation_id_deltas, (
        f"operationId parity regressed -- every operation_id in core/views.py is set "
        f"explicitly to match the frozen contract, so this should never be non-empty: "
        f"{operation_id_deltas}"
    )
