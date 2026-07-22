"""Tests for the error-envelope drop-in (errors.py). Pydantic only — no
FastAPI import anywhere in this file, matching errors.py itself."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from errors import (
    AppError,
    ConflictError,
    ErrorBody,
    ErrorCode,
    ErrorDetail,
    ErrorEnvelope,
    NotFoundError,
    PermissionDeniedError,
    RateLimitedError,
    UnauthenticatedError,
    ValidationFailedError,
)


# --- envelope serialization shape ------------------------------------------


def test_error_envelope_serializes_to_the_documented_shape():
    envelope = ErrorEnvelope(error=ErrorBody(code="not_found", message="Widget not found."))
    dumped = envelope.model_dump()

    assert dumped == {
        "error": {
            "code": "not_found",
            "message": "Widget not found.",
            "details": None,
        }
    }


def test_error_envelope_with_details():
    envelope = ErrorEnvelope(
        error=ErrorBody(
            code="validation_failed",
            message="Invalid request.",
            details=[ErrorDetail(field="email", message="not a valid email address")],
        )
    )
    dumped = envelope.model_dump()

    assert dumped["error"]["details"] == [{"field": "email", "message": "not a valid email address"}]


def test_error_detail_field_is_optional():
    detail = ErrorDetail(message="cross-field business rule violated")
    assert detail.field is None


def test_error_envelope_rejects_unknown_top_level_field():
    with pytest.raises(ValidationError):
        ErrorEnvelope(error=ErrorBody(code="x", message="y"), status=500)  # type: ignore[call-arg]


def test_error_body_rejects_unknown_field():
    with pytest.raises(ValidationError):
        ErrorBody(code="x", message="y", extra_field="z")  # type: ignore[call-arg]


def test_error_detail_rejects_unknown_field():
    with pytest.raises(ValidationError):
        ErrorDetail(message="y", unexpected="z")  # type: ignore[call-arg]


# --- ErrorCode: the frozen, machine-matchable enum --------------------------


def test_error_code_enum_has_the_canonical_members():
    assert {c.value for c in ErrorCode} == {
        "internal_error",
        "unauthenticated",
        "permission_denied",
        "not_found",
        "validation_failed",
        "conflict",
        "rate_limited",
    }


def test_error_code_is_a_str_subclass_and_serializes_as_a_plain_string():
    assert isinstance(ErrorCode.NOT_FOUND, str)
    envelope = ErrorEnvelope(error=ErrorBody(code=ErrorCode.NOT_FOUND, message="x"))
    assert envelope.model_dump()["error"]["code"] == "not_found"
    assert envelope.model_dump_json()  # sanity: round-trips through JSON


def test_error_body_accepts_a_valid_code_string_and_coerces_to_the_enum():
    body = ErrorBody(code="conflict", message="y")
    assert body.code is ErrorCode.CONFLICT


def test_error_body_rejects_an_unrecognized_code_string():
    with pytest.raises(ValidationError):
        ErrorBody(code="not_a_real_code", message="y")


# --- AppError base ----------------------------------------------------------


def test_app_error_uses_default_message_when_none_given():
    exc = AppError()
    assert exc.message == "An unexpected error occurred."
    assert exc.code == "internal_error"
    assert exc.status_code == 500


def test_app_error_uses_custom_message_when_given():
    exc = AppError("something specific broke")
    assert exc.message == "something specific broke"


def test_app_error_to_envelope_round_trips():
    exc = AppError("boom")
    envelope = exc.to_envelope()
    assert envelope.error.code == "internal_error"
    assert envelope.error.message == "boom"
    assert envelope.error.details is None


def test_app_error_is_a_real_exception_and_carries_its_message():
    with pytest.raises(AppError, match="boom"):
        raise AppError("boom")


def test_app_error_to_envelope_carries_details():
    exc = AppError("bad input", details=[ErrorDetail(field="name", message="too short")])
    envelope = exc.to_envelope()
    assert envelope.error.details == [ErrorDetail(field="name", message="too short")]


# --- concrete subclasses: code + status_code + default message -------------


@pytest.mark.parametrize(
    "exc_cls, expected_code, expected_status",
    [
        (UnauthenticatedError, "unauthenticated", 401),
        (PermissionDeniedError, "permission_denied", 403),
        (NotFoundError, "not_found", 404),
        (ValidationFailedError, "validation_failed", 422),
        (ConflictError, "conflict", 409),
        (RateLimitedError, "rate_limited", 429),
    ],
)
def test_concrete_exception_carries_correct_code_and_status(exc_cls, expected_code, expected_status):
    exc = exc_cls()
    assert exc.code == expected_code
    assert exc.status_code == expected_status
    assert exc.message  # every subclass has a non-empty default message


def test_concrete_exception_to_envelope_uses_its_own_code():
    exc = NotFoundError()
    envelope = exc.to_envelope()
    assert envelope.error.code == "not_found"
    assert envelope.model_dump() == {
        "error": {
            "code": "not_found",
            "message": "The requested resource was not found.",
            "details": None,
        }
    }


def test_concrete_exception_accepts_a_custom_message():
    exc = NotFoundError("Widget abc-123 was not found.")
    assert exc.message == "Widget abc-123 was not found."
    assert exc.to_envelope().error.message == "Widget abc-123 was not found."


def test_every_concrete_subclass_is_an_app_error():
    for exc_cls in (
        UnauthenticatedError,
        PermissionDeniedError,
        NotFoundError,
        ValidationFailedError,
        ConflictError,
        RateLimitedError,
    ):
        assert issubclass(exc_cls, AppError)
