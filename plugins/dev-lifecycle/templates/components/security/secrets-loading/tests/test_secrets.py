"""Tests for the secrets-loading drop-in. Values used throughout are
obviously fake (e.g. "s3cr3t-value-not-real") — no real credential ever
appears in this file.
"""

from __future__ import annotations

import logging
import sys

import pytest

import secrets as secrets_mod
from secrets import (
    MissingSecretsError,
    SecretNotFoundError,
    get_secret,
    validate_required,
)


@pytest.fixture(autouse=True)
def _reset_asm_cache():
    """Every test starts with no cached ASM client, and leaves none behind
    for the next test."""
    secrets_mod._reset_asm_client_cache_for_tests()
    yield
    secrets_mod._reset_asm_client_cache_for_tests()


class FakeSecretsManagerClient:
    """Stubs the narrow boto3 `secretsmanager` client surface this module
    calls (get_secret_value) — no boto3 dependency required to exercise
    the AWS Secrets Manager code path."""

    def __init__(self, store: dict[str, str]) -> None:
        self.store = store
        self.calls: list[str] = []

    def get_secret_value(self, *, SecretId: str) -> dict[str, str]:
        self.calls.append(SecretId)
        if SecretId not in self.store:
            raise KeyError(f"no such secret: {SecretId}")
        return {"SecretString": self.store[SecretId]}


# --- env-var layer -----------------------------------------------------


def test_get_secret_resolves_from_env(monkeypatch):
    monkeypatch.setenv("MY_FAKE_SECRET", "s3cr3t-value-not-real")
    assert get_secret("MY_FAKE_SECRET") == "s3cr3t-value-not-real"


def test_get_secret_missing_required_raises(monkeypatch):
    monkeypatch.delenv("DEFINITELY_UNSET_SECRET", raising=False)
    with pytest.raises(SecretNotFoundError) as exc_info:
        get_secret("DEFINITELY_UNSET_SECRET")
    assert exc_info.value.name == "DEFINITELY_UNSET_SECRET"


def test_get_secret_missing_optional_returns_default(monkeypatch):
    monkeypatch.delenv("UNSET_WITH_DEFAULT", raising=False)
    assert get_secret("UNSET_WITH_DEFAULT", required=False, default="fallback-fake") == "fallback-fake"


def test_get_secret_missing_optional_no_default_returns_none(monkeypatch):
    monkeypatch.delenv("UNSET_OPTIONAL", raising=False)
    assert get_secret("UNSET_OPTIONAL", required=False) is None


def test_get_secret_empty_env_value_treated_as_unset(monkeypatch):
    # An empty string is a common misconfiguration (e.g. `FOO=` in a shell
    # env file) — treat it the same as unset, not as "resolved to ''".
    monkeypatch.setenv("EMPTY_SECRET", "")
    with pytest.raises(SecretNotFoundError):
        get_secret("EMPTY_SECRET")


# --- validate_required fail-fast ---------------------------------------


def test_validate_required_passes_when_all_present(monkeypatch):
    monkeypatch.setenv("A_FAKE", "a-value")
    monkeypatch.setenv("B_FAKE", "b-value")
    validate_required(["A_FAKE", "B_FAKE"])  # must not raise


def test_validate_required_lists_every_missing_name(monkeypatch):
    monkeypatch.setenv("PRESENT_FAKE", "present-value")
    monkeypatch.delenv("MISSING_ONE", raising=False)
    monkeypatch.delenv("MISSING_TWO", raising=False)
    with pytest.raises(MissingSecretsError) as exc_info:
        validate_required(["PRESENT_FAKE", "MISSING_ONE", "MISSING_TWO"])
    assert set(exc_info.value.names) == {"MISSING_ONE", "MISSING_TWO"}


# --- never logs secret VALUES -------------------------------------------


def test_successful_resolution_never_logs_the_value(monkeypatch, caplog):
    monkeypatch.setenv("LOGGED_SECRET", "should-never-appear-in-logs")
    with caplog.at_level(logging.DEBUG, logger="secrets"):
        get_secret("LOGGED_SECRET")
    assert "should-never-appear-in-logs" not in caplog.text
    assert "LOGGED_SECRET" in caplog.text  # the NAME is fine to log


def test_missing_required_error_message_omits_value(monkeypatch):
    monkeypatch.delenv("NO_SUCH_SECRET", raising=False)
    with pytest.raises(SecretNotFoundError) as exc_info:
        get_secret("NO_SUCH_SECRET")
    # The message can only ever contain the name — there is no value to leak,
    # which is exactly the point: the error path never had one to log.
    assert "NO_SUCH_SECRET" in str(exc_info.value)


# --- AWS Secrets Manager fallback (stubbed client, no boto3 needed) ----


def test_asm_fallback_used_when_env_missing(monkeypatch):
    monkeypatch.delenv("ASM_ONLY_SECRET", raising=False)
    monkeypatch.setenv("SECRETS_BACKEND", "aws-secrets-manager")
    fake_client = FakeSecretsManagerClient({"ASM_ONLY_SECRET": "asm-fake-value"})

    assert get_secret("ASM_ONLY_SECRET", client=fake_client) == "asm-fake-value"
    assert fake_client.calls == ["ASM_ONLY_SECRET"]


def test_asm_fallback_respects_prefix(monkeypatch):
    monkeypatch.delenv("PREFIXED_SECRET", raising=False)
    monkeypatch.setenv("SECRETS_BACKEND", "aws-secrets-manager")
    monkeypatch.setenv("AWS_SECRETS_MANAGER_PREFIX", "prod/myapp/")
    fake_client = FakeSecretsManagerClient({"prod/myapp/PREFIXED_SECRET": "prefixed-fake-value"})

    assert get_secret("PREFIXED_SECRET", client=fake_client) == "prefixed-fake-value"


def test_asm_fallback_extracts_key_from_json_blob(monkeypatch):
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    monkeypatch.setenv("SECRETS_BACKEND", "aws-secrets-manager")
    fake_client = FakeSecretsManagerClient(
        {"DB_PASSWORD": '{"DB_PASSWORD": "structured-fake-value", "DB_USER": "app"}'}
    )

    assert get_secret("DB_PASSWORD", client=fake_client) == "structured-fake-value"


def test_env_takes_priority_over_asm(monkeypatch):
    # Layering order: env var always wins when present, ASM is a fallback
    # only, never a first choice.
    monkeypatch.setenv("SECRETS_BACKEND", "aws-secrets-manager")
    monkeypatch.setenv("BOTH_LAYERS_SECRET", "env-wins-fake-value")
    fake_client = FakeSecretsManagerClient({"BOTH_LAYERS_SECRET": "asm-should-not-win"})

    assert get_secret("BOTH_LAYERS_SECRET", client=fake_client) == "env-wins-fake-value"
    assert fake_client.calls == []  # never even called


def test_asm_not_consulted_when_backend_not_configured(monkeypatch):
    # Default backend is env-only — no accidental network calls just
    # because SECRETS_BACKEND happens to be unset.
    monkeypatch.delenv("SECRETS_BACKEND", raising=False)
    monkeypatch.delenv("UNCONFIGURED_BACKEND_SECRET", raising=False)
    with pytest.raises(SecretNotFoundError):
        get_secret("UNCONFIGURED_BACKEND_SECRET", client=FakeSecretsManagerClient({}))


# --- lazy boto3 import (no real boto3 required) -------------------------


def test_lazy_boto3_import_used_when_no_client_injected(monkeypatch):
    """Verifies the lazy-import path itself: with a fake `boto3` module
    planted in sys.modules (no real boto3 installed), calling get_secret
    without an explicit `client=` must reach boto3.client("secretsmanager", ...)
    exactly as the module's own _get_asm_client would."""
    calls: list[tuple[str, dict]] = []

    class _FakeBoto3Client:
        def get_secret_value(self, *, SecretId: str) -> dict[str, str]:
            return {"SecretString": "lazy-import-fake-value"}

    class _FakeBoto3Module:
        @staticmethod
        def client(service_name: str, region_name: str | None = None):
            calls.append((service_name, {"region_name": region_name}))
            return _FakeBoto3Client()

    monkeypatch.setitem(sys.modules, "boto3", _FakeBoto3Module())
    monkeypatch.setenv("SECRETS_BACKEND", "aws-secrets-manager")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.delenv("LAZY_IMPORT_SECRET", raising=False)

    result = get_secret("LAZY_IMPORT_SECRET")

    assert result == "lazy-import-fake-value"
    assert calls == [("secretsmanager", {"region_name": "us-east-1"})]


def test_asm_backend_without_boto3_installed_raises_clear_error(monkeypatch):
    """When SECRETS_BACKEND=aws-secrets-manager but boto3 truly isn't
    importable, the module raises a clear, actionable RuntimeError instead
    of a bare ImportError traceback."""
    monkeypatch.setitem(sys.modules, "boto3", None)  # forces ImportError on `import boto3`
    monkeypatch.setenv("SECRETS_BACKEND", "aws-secrets-manager")
    monkeypatch.delenv("NO_BOTO3_SECRET", raising=False)

    with pytest.raises(RuntimeError, match="requires boto3"):
        get_secret("NO_BOTO3_SECRET")


def test_asm_lookup_failure_falls_through_to_required_error(monkeypatch):
    monkeypatch.setenv("SECRETS_BACKEND", "aws-secrets-manager")
    monkeypatch.delenv("NOT_IN_ASM_EITHER", raising=False)
    fake_client = FakeSecretsManagerClient({})  # empty store -> lookup raises

    with pytest.raises(SecretNotFoundError):
        get_secret("NOT_IN_ASM_EITHER", client=fake_client)
