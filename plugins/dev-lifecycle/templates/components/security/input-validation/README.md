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
  `str_strip_whitespace=True`, `validate_assignment=True`, `strict=True`.
  The base every hardened input model extends.
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

`StrictModel` also sets `strict=True`, so Pydantic's lax-mode coercion is
off entirely: a JSON `"123"` string is **not** accepted for an `int` field,
`1`/`0` is **not** accepted for a `bool` field, and `"yes"`/`"on"`/`"true"`
strings are **not** accepted for a `bool` field either — every field must
arrive as its declared JSON type or the whole model fails validation. This
is deliberate, not an omission: JSON has real int and bool types, and an
external-input boundary should never treat "looks like the right type" the
same as "is the right type." A project that genuinely wants coercion for a
specific field opts back in per-field (Pydantic's `Field(strict=False)` or
an explicit `BeforeValidator`), not by weakening `StrictModel` globally.

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
trailing dot or trailing space (both silently stripped by Windows), a `:`
(the NTFS alternate-data-stream separator), a Windows reserved device name
(`CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9`, `LPT1`-`LPT9`, case-insensitive,
with or without an extension — `"con.txt"` is exactly as reserved as
`"con"`), a null byte, and control characters — a filename is a single path
*segment*, never a path. It validates the name only: still join the
validated result against a known-safe storage directory with a real
path-safe API (`pathlib.Path(base) / safe_name`, then confirm `.resolve()`
stays under `base`) as defense in depth, rather than trusting string
concatenation even after this check passes.

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

Beyond category-Cc controls, `no_control_chars()` also rejects a
deliberately narrow set of high-risk Unicode "format" (category Cf)
characters: the bidirectional override/isolate controls (`U+202A`-`U+202E`,
`U+2066`-`U+2069`) behind Trojan-Source-style attacks, where these
characters make displayed text read differently than the underlying byte
order (disguising a malicious identifier or filename as a benign one); the
zero-width marks (`U+200B`-`U+200F`), the BOM (`U+FEFF`), and the soft
hyphen (`U+00AD`) — all invisible-or-near-invisible characters usable to
smuggle content into an otherwise-plain string or evade a naive filter.
This is a named, bounded list, **not** a rejection of Unicode category Cf
wholesale — ordinary international text (`é`, `中`, emoji, and so on) is
untouched; only these specific attack-shaped characters are rejected.

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
and re-validating on assignment, `StrictModel`'s `strict=True` rejecting
lax-mode type coercion (`"123"` for an `int` field, `1` or `"yes"` for a
`bool` field) while still accepting well-typed values, `no_control_chars()`
rejecting the null byte / ESC / CR-LF / bell attack shapes *and* the bidi
override/isolate / zero-width / BOM / soft-hyphen attack shapes while still
accepting ordinary international text (accented Latin, CJK, emoji, mixed
scripts), `safe_filename()` rejecting every traversal shape
(`../../etc/passwd`, `..`, a subdirectory segment, Windows `\`-separators,
a leading dot, a null byte), every Windows reserved device name
(`CON`/`PRN`/`AUX`/`NUL`/`COM1`-`9`/`LPT1`-`9`, with or without an
extension), a trailing dot, a trailing space, and a `:`, while accepting a
plain filename and a name that merely *contains* a reserved word as a
substring (`"console.txt"`), `SafeIdentifier`/`Slug` pattern boundaries,
both size-limit helpers rejecting an oversize payload, and an end-to-end
composed model (`ExampleHardenedInput`) exercising all of the above
together plus the mass-assignment rejection.

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
- **`StrictModel` uses real strict mode (`strict=True`), not just
  `extra="forbid"`.** A project migrating existing code onto `StrictModel`
  should expect previously-tolerated coercions (numeric strings for `int`
  fields, `0`/`1` or `"yes"`/`"no"` for `bool` fields) to start failing
  validation — this is the intended effect at an external-input boundary,
  not a regression to work around by loosening the base model.
- **`no_control_chars` rejects a named, bounded list of Cf characters, not
  all of category Cf.** Unicode category Cf is large and includes marks
  that are part of normal text rendering in some scripts; rejecting the
  whole category would over-reject legitimate international input. Only
  the specific bidi-override/isolate, zero-width, BOM, and soft-hyphen
  characters documented above (and in the `_HIGH_RISK_FORMAT_CHARS`
  docstring in `validation.py`) are rejected.
