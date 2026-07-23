"""Conformance-proof tests for `core.exceptions.exception_handler` — Stage 4
Step 2 (#27), the acceptance core for this step. Every assertion here checks
the response body against a shape independently constructed from
`core.contract.errors` (the vendored contract source), not just "some 4xx/
5xx status" — see each test's own docstring for exactly what's cross-checked
and against what.

Fix round additions (below `test_empty_name_is_rejected_with_422`): the
review found real bugs where several exception paths escaped
`core.exceptions.exception_handler`'s mapping entirely and fell through to
a bare, un-enveloped 500 — a malformed (non-UUID) `item_id`, malformed JSON,
a disallowed HTTP method, and bad Basic-auth credentials. Every one of
those is exercised here via the REAL request path (DRF's `APIClient`
against the real `ItemViewSet`/throwaway conformance route), not by
asserting the model/handler function in isolation."""

from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

from core.contract.errors import AppError, ErrorEnvelope, NotFoundError

pytestmark = pytest.mark.django_db


def test_validation_error_is_422_and_matches_error_envelope_shape(api_client: APIClient) -> None:
    """`name=""` violates the frozen contract's `ItemCreate.name`
    `minLength: 1` (packages/api-client/openapi.json) — DRF's own
    `ValidationError` default status is 400; this asserts the handler
    reproduces FastAPI's 422 instead (see core/exceptions.py's module
    docstring, "422, not DRF's default 400"). The cross-check: parsing the
    raw response body through `ErrorEnvelope.model_validate` — the SAME
    vendored pydantic model `core/contract/errors.py` defines — must
    succeed (proving no extra/missing keys, correct types, a real
    `ErrorCode` member) and re-dumping it must reproduce the exact same
    JSON, byte-for-byte."""
    response = api_client.post("/items", {"name": ""}, format="json")

    assert response.status_code == 422
    body = response.json()

    envelope = ErrorEnvelope.model_validate(body)
    assert envelope.error.code.value == "validation_failed"
    assert envelope.model_dump(mode="json") == body

    assert any(d.field == "name" for d in envelope.error.details or [])


def test_not_found_error_matches_vendored_not_found_error_envelope(api_client: APIClient) -> None:
    """Builds the EXPECTED envelope directly from
    `core.contract.errors.NotFoundError` (the vendored exception class
    itself, not a re-implementation) and asserts the actual `GET
    /items/{missing_id}` response equals it exactly — the literal
    "cross-check ... against the vendored errors.py output for the same
    inputs" this step's instructions call for."""
    missing_id = uuid.uuid4()

    response = api_client.get(f"/items/{missing_id}")

    assert response.status_code == 404
    expected = NotFoundError(f"Item {missing_id} was not found.").to_envelope().model_dump(mode="json")
    assert response.json() == expected


@pytest.mark.urls("tests._conformance_urls")
def test_not_authenticated_is_401_and_matches_error_envelope_shape(api_client: APIClient) -> None:
    """No real route in this block raises `NotAuthenticated` yet (Stage 5,
    #28, is real auth) — exercised via a throwaway test-only route (see
    `tests/_conformance_urls.py`), the same pattern backend/fastapi's own
    `crashing_client` fixture uses for its 500 test."""
    response = api_client.get("/__test_only_401")

    assert response.status_code == 401
    body = response.json()
    envelope = ErrorEnvelope.model_validate(body)
    assert envelope.error.code.value == "unauthenticated"
    assert envelope.model_dump(mode="json") == body


@pytest.mark.urls("tests._conformance_urls")
def test_permission_denied_is_403_and_matches_error_envelope_shape(api_client: APIClient) -> None:
    response = api_client.get("/__test_only_403")

    assert response.status_code == 403
    body = response.json()
    envelope = ErrorEnvelope.model_validate(body)
    assert envelope.error.code.value == "permission_denied"
    assert envelope.model_dump(mode="json") == body


@pytest.mark.urls("tests._conformance_urls")
def test_unhandled_exception_returns_enveloped_500_without_leaking_message(
    crashing_client: APIClient,
) -> None:
    """Pins the SAME promise backend/fastapi's
    `test_unhandled_exception_returns_enveloped_500_without_leaking_message`
    (tests/test_error_envelope.py) pins there: a genuinely unhandled bug —
    not a deliberately-raised AppError — still renders `ErrorEnvelope` at
    500, and the exception's own message/type NEVER reaches the client."""
    response = crashing_client.get("/__test_only_crash")

    assert response.status_code == 500
    body = response.json()

    expected = AppError().to_envelope().model_dump(mode="json")
    assert body == expected
    assert "boom" not in body["error"]["message"]
    assert "RuntimeError" not in body["error"]["message"]


def test_item_response_never_includes_deleted_at(api_client: APIClient) -> None:
    created = api_client.post("/items", {"name": "Visible"}, format="json").json()
    assert "deleted_at" not in created

    fetched = api_client.get(f"/items/{created['id']}").json()
    assert "deleted_at" not in fetched

    listed = api_client.get("/items").json()
    for item in listed["items"]:
        assert "deleted_at" not in item


def test_empty_name_is_rejected_with_422(api_client: APIClient) -> None:
    response = api_client.post("/items", {"name": ""}, format="json")
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Fix round: paths that used to escape `exception_handler`'s mapping and
# fall through to a bare, un-enveloped 500. Every test below hits the REAL
# route through `APIClient`, not the handler function directly.
# ---------------------------------------------------------------------------


def test_malformed_uuid_path_is_404_not_500(api_client: APIClient) -> None:
    """BLOCKER fix: a non-UUID `item_id` (`django.core.exceptions.
    ValidationError`, raised inside `UUIDField`'s lookup coercion) used to
    escape `ItemViewSet.get_object()`'s `except (DoesNotExist, ValueError,
    TypeError)` entirely, reaching the client as a bare 500. Now caught
    (core/views.py) and rendered as the documented 404 `NotFoundError`
    envelope, byte-equal to what the vendored exception class itself would
    produce for the same message."""
    response = api_client.get("/items/not-a-uuid")

    assert response.status_code == 404
    expected = NotFoundError("Item not-a-uuid was not found.").to_envelope().model_dump(mode="json")
    assert response.json() == expected


def test_malformed_json_body_is_not_500(api_client: APIClient) -> None:
    """BLOCKER fix: a body that fails JSON parsing raises DRF's `ParseError`
    (an `APIException` with no explicit branch above) — this used to fall
    through the old catch-all straight to a bare 500. Now mapped by
    `exception_handler`'s generic `APIException` branch: DRF's own
    `ParseError.status_code` (400) is kept as the real status (documented,
    honest divergence from FastAPI's 422 for the same malformed-body case
    — see this block's README, "Conformance"), and the body is a real
    `ErrorEnvelope` with `code=validation_failed`, not an unhandled 500."""
    response = api_client.post("/items", data="{not valid json", content_type="application/json")

    assert response.status_code != 500
    assert response.status_code == 400
    body = response.json()
    envelope = ErrorEnvelope.model_validate(body)
    assert envelope.error.code.value == "validation_failed"
    assert envelope.model_dump(mode="json") == body


def test_put_is_405_not_500(api_client: APIClient) -> None:
    """BLOCKER fix: `MethodNotAllowed` (an `APIException` with no explicit
    branch above) used to fall through to a bare 500. `ItemViewSet.
    http_method_names` (core/views.py, this fix round) also now excludes
    `"put"` entirely, so a `PUT` request never reaches `update()` — Django's
    own `dispatch()` routes it straight to `http_method_not_allowed()`,
    which `exception_handler`'s generic `APIException` branch renders as a
    real `ErrorEnvelope` at the correct 405 status (kept real, not folded
    into 422/400 — see core/exceptions.py's own module docstring)."""
    created = api_client.post("/items", {"name": "Original"}, format="json").json()

    response = api_client.put(f"/items/{created['id']}", {"name": "Replaced"}, format="json")

    assert response.status_code == 405
    body = response.json()
    envelope = ErrorEnvelope.model_validate(body)
    assert envelope.error.code.value == "validation_failed"
    assert envelope.model_dump(mode="json") == body

    # PATCH is still the real, contract-defined update path.
    patch_response = api_client.patch(f"/items/{created['id']}", {"name": "Renamed"}, format="json")
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "Renamed"


@pytest.mark.urls("tests._conformance_urls")
def test_bad_basic_auth_credentials_are_401_not_500(api_client: APIClient) -> None:
    """BLOCKER fix: `AuthenticationFailed` (bad/malformed credentials, an
    `APIException` distinct from `NotAuthenticated`'s "no credentials at
    all" — the latter already had its own explicit branch above) used to
    fall through to a bare 500. No real route in this block runs
    `BasicAuthentication` any more (`DEFAULT_AUTHENTICATION_CLASSES = []`,
    config/settings.py, this fix round's HIGH fix) — exercised via a
    throwaway test-only route that opts back into it (see
    `tests/_conformance_urls.py`), the same pattern the 401/403/500 tests
    above already use."""
    api_client.credentials(HTTP_AUTHORIZATION="Basic not-a-valid-base64-credential")

    response = api_client.get("/__test_only_basic_auth")

    assert response.status_code == 401
    body = response.json()
    envelope = ErrorEnvelope.model_validate(body)
    assert envelope.error.code.value == "unauthenticated"
    assert envelope.model_dump(mode="json") == body
