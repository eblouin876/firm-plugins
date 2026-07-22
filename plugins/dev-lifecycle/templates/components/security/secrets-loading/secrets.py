"""Framework-neutral secrets loading: process env first, an optional AWS
Secrets Manager fallback second, and this module never reads a `.env` file
itself. Canon: references/security/secrets-management.md (this module is
the mechanism behind that doc's environment table — "Local dev reads
`.env` via the framework's standard loader," never bespoke secret-loading
code per block, which is exactly why this module refuses to parse `.env`
itself — see "Why no .env parsing" in the component README) and
references/security/secure-baseline.md ("Secrets never in code or
images").

Drop-in: copy this file into app/core/security/secrets.py. Stdlib only —
boto3 is imported lazily, and only once the AWS Secrets Manager backend is
actually configured (SECRETS_BACKEND=aws-secrets-manager), so local dev
and unit tests never need it installed.
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
    except Exception:
        # Deliberately broad: boto3 raises its own generated ClientError
        # subclasses (ResourceNotFoundException, AccessDeniedException, ...)
        # that this module has no compile-time dependency on. Log the NAME
        # only — never the exception's str() on a path an attacker-shaped
        # secret_id could influence.
        logger.warning("secret %r not found in AWS Secrets Manager", name)
        return None
    value = response.get("SecretString")
    if value is None:
        return None
    # ASM sometimes stores a structured credential (DB user+password+host)
    # as a JSON blob. If the value decodes as an object with a key matching
    # `name`, return that field; otherwise return the raw SecretString
    # as-is (the common single-value-secret case).
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value
    if isinstance(parsed, dict) and name in parsed:
        return str(parsed[name])
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
