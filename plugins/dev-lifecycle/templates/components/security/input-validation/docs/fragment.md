<!-- fragment: block:components/security/input-validation -->

## Setup
Copy `validation.py` into `app/core/security/validation.py`. Extend
`StrictModel` for every hardened request/service-layer model; reach for the
provided `Annotated` types (`SafeIdentifier`, `Slug`, `SafeText`,
`SafeFilename`, `Email`, `ShortStr`) instead of hand-rolled field
constraints. Using `Email`? Add the `pydantic[email]` extra
(`email-validator`) — it isn't required by the rest of this module.

## Maintenance
DRF serializers stay DRF at the HTTP request boundary — this module targets
the shared/service layer underneath both the FastAPI and Django/DRF stacks,
not a replacement for `serializers.Serializer`.
