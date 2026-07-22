"""Pins two things Stage 3 Step 4 (#26) added: `app/export_openapi.py`
works without a live database, and `app/main.py`'s
`_install_error_envelope_openapi` fixup makes the exported schema describe
the 422/404 shapes this app actually sends (`ErrorEnvelope`), not
FastAPI's un-remapped native `HTTPValidationError`. This is also the
contract `packages/api-client`'s regenerated client is built against — a
regression here silently breaks that client's error typing too."""

from __future__ import annotations

from app.core.errors import ErrorEnvelope
from app.export_openapi import export_openapi_schema


def test_export_openapi_schema_does_not_require_a_live_database() -> None:
    """`export_openapi_schema()` builds its own app via `create_app()`
    directly (never the module-level `app.main.app` singleton, never a
    running ASGI server/lifespan) — this must succeed with no real
    Postgres/DATABASE_URL reachable, which is exactly the environment a CI
    job or a fresh clone running `python -m app.export_openapi` has."""
    schema = export_openapi_schema()
    assert schema["openapi"].startswith("3.1")
    assert schema["info"]["title"]


def test_exported_schema_documents_error_envelope_not_native_validation_shape() -> None:
    schema = export_openapi_schema()
    schemas = schema["components"]["schemas"]

    assert "ErrorEnvelope" in schemas
    assert "ErrorBody" in schemas
    assert "ErrorDetail" in schemas
    # FastAPI's native validation-error models must not survive once
    # nothing in the schema references them any more (see
    # _install_error_envelope_openapi's docstring in app/main.py).
    assert "HTTPValidationError" not in schemas
    assert "ValidationError" not in schemas

    error_envelope_ref = {"$ref": "#/components/schemas/ErrorEnvelope"}

    def _422_schema(path: str, method: str) -> dict:
        response = schema["paths"][path][method]["responses"]["422"]
        return response["content"]["application/json"]["schema"]

    # Every operation with a request body/params gets FastAPI's automatic
    # 422 — spot-check a representative few rather than every operation.
    assert _422_schema("/items", "get") == error_envelope_ref
    assert _422_schema("/items", "post") == error_envelope_ref
    assert _422_schema("/items/{item_id}", "get") == error_envelope_ref

    # NotFoundError's 404 is documented explicitly at the items.py call
    # site (not by the central 422 fixup) — confirm it also resolved.
    for method in ("get", "patch", "delete"):
        response_404 = schema["paths"]["/items/{item_id}"][method]["responses"]["404"]
        assert response_404["content"]["application/json"]["schema"] == error_envelope_ref


def test_error_envelope_json_schema_matches_installed_schema() -> None:
    """Sanity check the installed `ErrorEnvelope` schema in components
    isn't some hand-drifted copy — it's produced from the real Pydantic
    model, so its `required` fields match `ErrorEnvelope` itself."""
    schema = export_openapi_schema()
    envelope_schema = schema["components"]["schemas"]["ErrorEnvelope"]
    assert envelope_schema["required"] == ["error"]
    assert ErrorEnvelope.model_fields.keys() == {"error"}
