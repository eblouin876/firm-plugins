"""Framework-neutral input validation built on Pydantic v2: a strict model
base and a set of hardened field types/validators for the attack shapes
every external-input boundary needs to reject (control-character
injection, path traversal, oversize payloads). Canon:
references/security/secure-baseline.md ("Input validation & output
encoding") and references/security/attack-surfaces.md ("Input channels",
"File uploads").

Drop-in: copy this file into app/core/security/validation.py. Pydantic v2
only (pinned references/compatibility-matrix.md, Backend — Python:
2.13.x) — the one validation dependency both the FastAPI and Django/DRF
stacks in this kit carry. DRF serializers stay DRF at the HTTP request
boundary; this module is for the shared/service layer underneath both
(see the component README's "Django/DRF" note — this file deliberately
contains no DRF code).

Note: the `Email` type re-exports Pydantic's own `EmailStr`, which in turn
requires the `email-validator` package (the `pydantic[email]` extra) to be
installed *at the point a model using it is actually constructed* — not at
import time of this module. A project that uses `Email` adds that extra;
one that doesn't never needs it.
"""

from __future__ import annotations

import unicodedata
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, StringConstraints

# ---------------------------------------------------------------------------
# Strict model base
# ---------------------------------------------------------------------------


class StrictModel(BaseModel):
    """Base for every hardened input model: unknown fields are a hard
    error (extra="forbid") instead of being silently dropped, so mass-
    assignment and schema drift both fail loudly instead of quietly
    passing extra client data through. Whitespace is stripped by default,
    and re-assigning an attribute on an already-constructed instance
    re-validates it too (validate_assignment) — a model can't be built
    valid and then mutated invalid."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


# ---------------------------------------------------------------------------
# Free-text validators (reject, don't silently mutate)
# ---------------------------------------------------------------------------


def no_control_chars(value: str) -> str:
    """Rejects any Unicode control character (category Cc — the C0 set,
    including NUL and DEL) anywhere in the string. Deliberately rejects
    rather than strips: a caller-visible ValueError beats a silently
    mutated value that hides a log-injection or terminal-escape-injection
    attempt from whoever reads the resulting report later."""
    for ch in value:
        if unicodedata.category(ch) == "Cc":
            raise ValueError("value must not contain control characters")
    return value


_PATH_TRAVERSAL_MARKERS = ("..", "/", "\\")


def safe_filename(value: str) -> str:
    """Validates a bare filename — a single path SEGMENT, never a path:
    rejects traversal shapes (`..`, any `/` or `\\` separator), a leading
    dot (dotfile/hidden-file smuggling), a null byte, and control
    characters. This validates the name only — still join it against a
    known-safe storage directory with a real path-safe API
    (`pathlib.Path(base) / safe_name`, then confirm `.resolve()` stays
    under `base`) rather than trusting string concatenation, as defense
    in depth on top of this check, not instead of it."""
    if not value or value in (".", ".."):
        raise ValueError("filename must not be empty, '.', or '..'")
    if "\x00" in value:
        raise ValueError("filename must not contain a null byte")
    for marker in _PATH_TRAVERSAL_MARKERS:
        if marker in value:
            raise ValueError(f"filename must not contain {marker!r}")
    if value.startswith("."):
        raise ValueError("filename must not start with '.'")
    return no_control_chars(value)


# ---------------------------------------------------------------------------
# Reusable Annotated field types
# ---------------------------------------------------------------------------

# A "reasonable" bounded short string — most name/title/label fields. Not
# a universal default; pick the bound that matches the actual field.
ShortStr = Annotated[str, StringConstraints(min_length=1, max_length=255, strip_whitespace=True)]

# Bounded free text that also rejects embedded control characters — the
# shape for a comment/description/message-body field.
SafeText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=10_000, strip_whitespace=True),
    AfterValidator(no_control_chars),
]

# A safe identifier: must start with a letter or underscore, then
# letters/digits/underscore — no spaces or path/shell-meaningful
# characters. Good for internal keys, usernames, environment-variable-
# shaped names.
SafeIdentifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$"),
]

# A URL-safe slug: lowercase letters/digits separated by single hyphens —
# no leading/trailing/doubled hyphen. The conventional shape for
# permalinks and path segments.
Slug = Annotated[
    str,
    StringConstraints(min_length=1, max_length=200, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"),
]

# Pydantic's own EmailStr (backed by the `email-validator` package it
# depends on — see the module docstring) is the e-mail validator this
# module standardizes on, re-exported here so every model imports one
# thing from one place.
Email = EmailStr

# A path-traversal-safe bare filename, bounded to a sane length.
SafeFilename = Annotated[
    str,
    StringConstraints(min_length=1, max_length=255),
    AfterValidator(safe_filename),
]


# ---------------------------------------------------------------------------
# Size / limit helpers
# ---------------------------------------------------------------------------


def check_max_bytes(payload: bytes, *, max_bytes: int, label: str = "payload") -> bytes:
    """Fail fast on an oversize raw payload — e.g. an upload body read
    before it's ever handed to a Pydantic model, where a length
    constraint on a str field can't help because the attack is in the
    raw bytes read off the wire. Raises ValueError, the same exception
    family Pydantic validators raise, so it composes as an
    AfterValidator body too."""
    if len(payload) > max_bytes:
        raise ValueError(f"{label} exceeds the {max_bytes}-byte limit ({len(payload)} bytes read)")
    return payload


def check_max_length(value: str, *, max_length: int, label: str = "value") -> str:
    """Same idea as check_max_bytes, for a str already in hand outside a
    model — e.g. to fail with a clearer message before constructing one,
    rather than relying only on the model's own field constraint."""
    if len(value) > max_length:
        raise ValueError(f"{label} exceeds {max_length} characters ({len(value)} characters)")
    return value


# ---------------------------------------------------------------------------
# Illustrative composition (copy the pattern into a real request model)
# ---------------------------------------------------------------------------


class ExampleHardenedInput(StrictModel):
    """Shows the field types above wired into one model. Not itself part
    of any app's schema — copy the pattern, not this class, into a real
    request/service-layer model. Deliberately omits an Email field so
    this module (and its tests) never require the `email-validator`
    extra; add `email: Email` in a project that installs it."""

    username: SafeIdentifier
    slug: Slug
    bio: SafeText
    filename: SafeFilename
