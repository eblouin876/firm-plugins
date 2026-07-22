<!--
block: components/security/input-validation  # catalog component
needs:
  - pydantic v2 (2.13.x): the sole runtime dependency, pinned per references/compatibility-matrix.md's Backend — Python row; both the FastAPI and Django/DRF stacks in this kit already carry it
  - email-validator (optional): only required if a consuming model actually uses the `Email` type; not needed to import or use the rest of this module
exposes:
  - StrictModel — the extra="forbid" base every hardened input model extends
  - SafeIdentifier, Slug, ShortStr, SafeText, SafeFilename, Email — reusable Annotated field types
  - no_control_chars(value), safe_filename(value) — the two reusable validator functions the Annotated types wrap
  - check_max_bytes(payload, *, max_bytes, label), check_max_length(value, *, max_length, label) — size/limit helpers for raw input ahead of model construction
  - its co-located doc fragment: docs/fragment.md
versions-pinned-to: references/compatibility-matrix.md
last-verified: 2026-07-22
provenance: manual
-->

# input-validation

A framework-neutral, drop-in `validation.py` built on Pydantic v2: a
strict-mode model base and a set of hardened field types for the attack
shapes every external-input boundary needs to reject. Lives at
`templates/components/security/input-validation/` in this repo; Stage 3-4
backend blocks copy `validation.py` verbatim into
`app/core/security/validation.py`. Embodies the "Input validation & output
encoding" section of `references/security/secure-baseline.md` and the
"Input channels" / "File uploads" entries of
`references/security/attack-surfaces.md`'s HTTP API section.

This is a **catalog component** (`template-author`'s partial-contract kind),
not an app-layer template block.

## Contents
- Composition contract
- StrictModel: reject, don't silently drop
- The hardened field types
- Reject, don't sanitize-and-continue
- Django/DRF note
- Testing
- Judgment calls

## Composition contract

**NEEDS**
- **Pydantic v2, 2.13.x** — the sole runtime dependency, pinned per
  `references/compatibility-matrix.md`'s Backend — Python row. Both the
  FastAPI and Django/DRF stacks this kit supports already carry Pydantic v2
  (FastAPI directly; DRF for the shared/service layer this component targets
  — see "Django/DRF note" below), so this component adds no new dependency
  to either stack.
- **`email-validator` (optional)** — only required at the moment a
  consuming model actually constructs an instance using the `Email` type
  (Pydantic's `EmailStr` imports it lazily, at schema-build time, not at
  this module's import time). A project that never uses `Email` never needs
  it; one that does adds the `pydantic[email]` extra.

**EXPOSES**
- `StrictModel` — a `BaseModel` subclass with `extra="forbid"`,
  `str_strip_whitespace=True`, `validate_assignment=True`. The base every
  hardened input model extends.
- Reusable `Annotated` field types: `ShortStr`, `SafeText`, `SafeIdentifier`,
  `Slug`, `Email`, `SafeFilename` — import and use directly as a field's
  type annotation.
- `no_control_chars(value)`, `safe_filename(value)` — the two validator
  functions the `Annotated` types above wrap via `AfterValidator`; usable
  standalone (e.g. as a `field_validator` body) when a project needs the
  check without the paired length constraint.
- `check_max_bytes(payload, *, max_bytes, label="payload")`,
  `check_max_length(value, *, max_length, label="value")` — plain functions
  for bounding a raw payload *before* it's handed to a Pydantic model (a
  streamed upload body, for instance, where the attack is in raw bytes a
  `str` field's `max_length` never sees).
- Its co-located doc fragment: `docs/fragment.md`.

## StrictModel: reject, don't silently drop

Pydantic's default (`extra="ignore"`) silently drops fields a model doesn't
declare — convenient, but it means a client that sends `{"is_admin": true}`
alongside a legitimate field gets no error, just silent discarding. That
hides schema drift and makes a mass-assignment attempt indistinguishable
from a typo in the request. `StrictModel` sets `extra="forbid"` instead: any
undeclared field is a hard `ValidationError`. `validate_assignment=True`
closes the matching gap on the other end — a model built valid and then
mutated (`instance.field = bad_value`) re-validates on assignment rather
than silently holding an invalid value afterward.

## The hardened field types

| Type | Shape | Use for |
| --- | --- | --- |
| `ShortStr` | 1-255 chars, whitespace-stripped | Names, titles, short labels |
| `SafeText` | 1-10,000 chars, no control characters | Comments, descriptions, message bodies |
| `SafeIdentifier` | `^[A-Za-z_][A-Za-z0-9_]*$`, ≤64 chars | Internal keys, usernames, env-var-shaped names |
| `Slug` | `^[a-z0-9]+(?:-[a-z0-9]+)*$`, ≤200 chars | URL permalinks, path segments |
| `Email` | Pydantic's `EmailStr` | E-mail addresses (needs the `email-validator` extra) |
| `SafeFilename` | ≤255 chars, traversal-safe (see below) | A bare uploaded/stored file's basename |

`safe_filename()` rejects `..`, any `/` or `\` separator, a leading dot, a
null byte, and control characters — a filename is a single path *segment*,
never a path. It validates the name only: still join the validated result
against a known-safe storage directory with a real path-safe API
(`pathlib.Path(base) / safe_name`, then confirm `.resolve()` stays under
`base`) as defense in depth, rather than trusting string concatenation even
after this check passes.

## Reject, don't sanitize-and-continue

`no_control_chars()` and `safe_filename()` both **raise** on a bad shape
rather than stripping the offending characters and returning a "cleaned"
value. A silently-mutated value that still validates hides the fact an
attack shape was submitted at all — from logs, from the caller, from
whoever debugs the resulting report later. A caller-visible
`ValidationError` is the correct outcome for "this input was actively
malformed," distinct from "this input needs light normalization" (which
`str_strip_whitespace` on `StrictModel` still handles automatically for
plain leading/trailing whitespace).

## Django/DRF note

This module is deliberately thin here: **DRF serializers stay DRF** at the
HTTP request boundary — this component is not a replacement for
`serializers.Serializer`/`ModelSerializer` and contains no DRF code. Use
`StrictModel` and the hardened field types instead in the
**shared/service layer** underneath both stacks: business logic, background
job payload validation, or anywhere a Django project already reaches for
Pydantic for a non-DRF-request shape. A DRF view's own serializer remains
the validation layer for its request/response cycle, per
`references/backend/drf.md`.

## Testing

`tests/test_validation.py` covers: `StrictModel` rejecting an unknown field
and re-validating on assignment, `no_control_chars()` rejecting the null
byte / ESC / CR-LF / bell attack shapes, `safe_filename()` rejecting every
traversal shape (`../../etc/passwd`, `..`, a subdirectory segment, Windows
`\`-separators, a leading dot, a null byte) while accepting a plain
filename, `SafeIdentifier`/`Slug` pattern boundaries, both size-limit
helpers rejecting an oversize payload, and an end-to-end composed model
(`ExampleHardenedInput`) exercising all of the above together plus the
mass-assignment rejection.

Run: `uv run --python 3.13 --with pydantic --with pytest -- pytest templates/components/security/input-validation/tests/ -q`
(no `email-validator` extra installed for this run — deliberate; see
"Judgment calls").

## Judgment calls

- **`Email` is exported but never exercised in a model in this component's
  own tests.** The firm-wide verification command
  (`uv run --python 3.13 --with pydantic --with pytest`) does not install
  `email-validator`, and Pydantic's `EmailStr` only imports it at
  schema-build time (when a model using it is defined/constructed) — not at
  this module's own import time. Building a test model with an `Email`
  field would make this component's test suite fail under the specified
  verification command. `Email = EmailStr` is still exported for a
  consuming project that installs the extra; the component's own tests
  exercise every other type instead. Documented rather than silently
  dropping the type.
- **`no_control_chars`/`safe_filename` reject rather than sanitize.** See
  "Reject, don't sanitize-and-continue" above — a deliberate security
  posture choice, not an oversight.
