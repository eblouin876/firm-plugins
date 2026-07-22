"""Framework-neutral secrets loading: process env first, an optional AWS
Secrets Manager fallback second, and this module never reads a `.env` file
itself. Canon: references/security/secrets-management.md (this module is
the mechanism behind that doc's environment table — "Local dev reads
`.env` via the framework's standard loader," never bespoke secret-loading
code per block, which is exactly why this module refuses to parse `.env`
itself — see "Why no .env parsing" in the component README) and
references/security/secure-baseline.md ("Secrets never in code or
images").

Drop-in: copy this file into app/core/security/secret_store.py. Stdlib
only — boto3 is imported lazily, and only once the AWS Secrets Manager
backend is actually configured (SECRETS_BACKEND=aws-secrets-manager), so
local dev and unit tests never need it installed.

Named `secret_store.py`, not `secrets.py`: this module provides no
stdlib-`secrets`-module functionality (no token/password generation), so
shadowing that stdlib module's name on `sys.path` once this file is copied
into a project is pure downside with no compensating benefit — see the
component README's "Judgment calls" for the full rationale.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Iterable, Protocol

logger = logging.getLogger(__name__)

_ASM_BACKEND = "aws-secrets-manager"
_ENV_ONLY_BACKEND = "env"


class SecretNotFoundError(LookupError):
    """Raised when a required secret cannot be resolved by any configured
    layer. Never includes the attempted value — only the secret's NAME is
    ever safe to surface in an error message or a log line."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"required secret {name!r} was not found in any configured layer")


class MissingSecretsError(LookupError):
    """Raised by validate_required(), listing every missing secret NAME at
    once (not just the first) so a misconfigured environment fails loudly
    and completely at startup rather than one request-time surprise at a
    time."""

    def __init__(self, names: list[str]) -> None:
        self.names = names
        super().__init__("missing required secret(s): " + ", ".join(sorted(names)))


class SecretShapeError(LookupError):
    """Raised when a value fetched from AWS Secrets Manager decodes as a
    JSON object but that object has no top-level key matching the
    requested secret NAME. Returning the raw JSON blob in that case (an
    earlier version of this module's behavior) would silently hand a
    caller a multi-field JSON string as if it were the single secret value
    it asked for — a shape mismatch between what's stored and what's
    requested is a configuration error worth failing loudly and
    immediately on, not guessing through. Never includes the secret's
    VALUE — only its name."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(
            f"secret {name!r} resolved to a JSON object in AWS Secrets "
            "Manager with no top-level key matching that name; store it as "
            "a scalar value, or as a JSON object with a top-level key "
            "named exactly the secret's name"
        )


class SecretsManagerClient(Protocol):
    """The narrow boto3 `secretsmanager` client surface this module calls.
    A Protocol, not boto3's own type — lets tests stub it with a plain fake
    object without installing boto3 at all. See the component's tests/ for
    the fake used to cover the AWS Secrets Manager path."""

    def get_secret_value(self, *, SecretId: str) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class SecretsConfig:
    """Resolved from process env at call time, not cached at import time —
    so tests (and a long-lived process reacting to a config reload) can
    change os.environ without reload tricks."""

    backend: str
    asm_prefix: str
    asm_region: str | None

    @classmethod
    def from_env(cls) -> SecretsConfig:
        backend = os.environ.get("SECRETS_BACKEND", _ENV_ONLY_BACKEND).strip().lower()
        return cls(
            backend=backend,
            asm_prefix=os.environ.get("AWS_SECRETS_MANAGER_PREFIX", ""),
            asm_region=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"),
        )


_asm_client_cache: SecretsManagerClient | None = None


def _get_asm_client(region: str | None) -> SecretsManagerClient:
    """Lazily imports boto3 — only reached when SECRETS_BACKEND is actually
    set to aws-secrets-manager. Local dev and any test that never enables
    the ASM backend never needs boto3 installed."""
    global _asm_client_cache
    if _asm_client_cache is not None:
        return _asm_client_cache
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError(
            "SECRETS_BACKEND=aws-secrets-manager requires boto3; install it "
            "(`uv add boto3`) or unset SECRETS_BACKEND for env-only resolution."
        ) from exc
    _asm_client_cache = boto3.client("secretsmanager", region_name=region)
    return _asm_client_cache


def _reset_asm_client_cache_for_tests() -> None:
    """Test-only hook: clears the cached boto3/fake client between tests.
    Not part of this module's public contract."""
    global _asm_client_cache
    _asm_client_cache = None


def _error_type_name(exc: Exception) -> str:
    """Cheap, best-effort identification of an ASM lookup failure's TYPE —
    never its message/value, which could carry secret-adjacent detail this
    module has no way to vet. Prefers a boto3 ClientError's own error code
    (e.g. "AccessDeniedException" vs "ResourceNotFoundException") when it's
    cheaply available on the exception object (no botocore import needed —
    just reads the `.response["Error"]["Code"]` shape boto3's ClientError
    always carries); falls back to the exception's own class name
    otherwise (e.g. a network-level exception, or the fake client's own
    exception type in tests). This is what lets an operator tell "IAM
    misconfiguration" (AccessDeniedException) apart from "the secret
    genuinely doesn't exist" (ResourceNotFoundException) from the log line
    alone, without ever logging the secret_id or any exception text that
    could echo attacker-influenced input."""
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        code = response.get("Error", {}).get("Code")
        if code:
            return str(code)
    return type(exc).__name__


def _fetch_from_asm(
    name: str,
    config: SecretsConfig,
    *,
    client: SecretsManagerClient | None = None,
) -> str | None:
    secret_id = f"{config.asm_prefix}{name}"
    resolved_client = client if client is not None else _get_asm_client(config.asm_region)
    try:
        response = resolved_client.get_secret_value(SecretId=secret_id)
    except Exception as exc:
        # Deliberately broad: boto3 raises its own generated ClientError
        # subclasses (ResourceNotFoundException, AccessDeniedException, ...)
        # that this module has no compile-time dependency on. Log the NAME
        # and the exception's TYPE only — never its str()/message, which on
        # a path an attacker-shaped secret_id could influence might echo
        # more than intended. The type name (or ClientError code) is enough
        # to tell an IAM misconfiguration apart from a genuinely missing
        # secret without ever risking a leaked detail.
        logger.warning(
            "secret %r not found in AWS Secrets Manager (%s)", name, _error_type_name(exc)
        )
        return None
    value = response.get("SecretString")
    if value is None:
        return None
    # ASM sometimes stores a structured credential (DB user+password+host)
    # as a JSON blob. If the value decodes as an object with a key matching
    # `name`, return that field; a scalar (non-dict) value returns as-is
    # (the common single-value-secret case). A dict that does NOT contain
    # a matching key is a shape mismatch worth failing loudly on — see
    # SecretShapeError — rather than silently handing back the raw
    # multi-field JSON blob as if it were the single requested value.
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value
    if isinstance(parsed, dict):
        if name in parsed:
            return str(parsed[name])
        raise SecretShapeError(name)
    return value


def get_secret(
    name: str,
    *,
    required: bool = True,
    default: str | None = None,
    client: SecretsManagerClient | None = None,
) -> str | None:
    """Resolve one secret by NAME, layered: process env first, then AWS
    Secrets Manager if SECRETS_BACKEND=aws-secrets-manager is configured.

    Never logs or raises with the resolved VALUE — only `name` ever appears
    in a log line or an exception message.

    `client` is a test-only injection point (a fake SecretsManagerClient);
    application code should not pass it — let the module manage its own
    lazily-created boto3 client.

    Can raise `SecretShapeError` (not caught here, deliberately — it's a
    configuration error, not a "missing" outcome) when the ASM layer is
    consulted and the stored value decodes as a JSON object with no
    top-level key matching `name`.
    """
    logger.debug("resolving secret %r", name)
    value = os.environ.get(name)
    if value:
        return value

    config = SecretsConfig.from_env()
    if config.backend == _ASM_BACKEND:
        value = _fetch_from_asm(name, config, client=client)
        if value:
            return value

    if default is not None:
        return default
    if required:
        logger.error("required secret %r was not found in any configured layer", name)
        raise SecretNotFoundError(name)
    return None


def validate_required(names: Iterable[str]) -> None:
    """Fail-fast startup check: resolve every NAME in `names`, raising
    MissingSecretsError listing every missing one at once — not just the
    first — so a misconfigured environment fails loudly and completely
    before the app starts serving traffic, never deep inside a request."""
    names = list(names)
    missing: list[str] = []
    for name in names:
        try:
            get_secret(name, required=True)
        except SecretNotFoundError:
            missing.append(name)
    if missing:
        logger.error("startup secret validation failed, missing: %s", ", ".join(sorted(missing)))
        raise MissingSecretsError(missing)
    logger.info("startup secret validation passed for %d secret(s)", len(names))
