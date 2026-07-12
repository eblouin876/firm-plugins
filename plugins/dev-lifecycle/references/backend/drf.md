<!--
library: djangorestframework
versions-covered: "DRF 3.x on Django 5.x"   # DRF 3.17.1, verified against Django 4.2–6.0 / Python 3.10+
last-verified: 2026-07-12
provenance: auto-generated (pending review)
sources:
  - https://www.django-rest-framework.org/
  - https://pypi.org/project/djangorestframework/
  - https://github.com/encode/django-rest-framework/releases
-->

# Django REST Framework conventions

DRF-specific idioms for JSON APIs layered on Django. Load after detecting `rest_framework` in `INSTALLED_APPS` or `djangorestframework` in the manifest. Complements `django.md` (do not repeat generic Django/ORM/security guidance) and is subordinate to the project's existing conventions.

## Contents
- Version check
- Serializers
- Validation
- Nested serializers & the N+1 trap
- Views: which flavor
- Permissions & queryset scoping
- Authentication
- Pagination
- Throttling, filtering, versioning
- Browsable API
- Error handling
- Testing
- The async caveat

## Version check (do this first)
- **Current: DRF 3.17.x** — requires **Python 3.10+** and **Django 4.2+** (supports 4.2, 5.0, 5.1, 5.2 LTS, 6.0). 3.17 dropped Python 3.9 and added 3.14.
- Confirm from the lockfile: `python -c "import rest_framework; print(rest_framework.VERSION)"`. Match the installed line's idioms.

## Serializers
- `ModelSerializer` for straight model mapping; plain `Serializer` when the shape diverges from the model (composed data, write-only actions).
- **Always declare `fields` explicitly.** Never `fields = '__all__'` — it silently leaks columns added later (tokens, internal flags). List `read_only_fields` for server-owned data (`id`, timestamps, `owner`).
- Separate read vs write serializers when they diverge; override `get_serializer_class` on the view rather than branching inside one serializer.

## Validation
- Field-level: `validate_<field>(self, value)`. Cross-field / object-level: `validate(self, attrs)`. Return the (possibly mutated) value/attrs; raise `serializers.ValidationError` on failure.
- Put invariants here, not in the view. Don't re-implement DB constraints the model already enforces — let `UniqueValidator`/model validation surface them.

## Nested serializers & the N+1 trap
- Nesting a serializer over a relation issues one query per parent row. **Annotate the view's `queryset` with `select_related` (FK/one-to-one) / `prefetch_related` (reverse/M2M)** covering every nested relation.
- Writable nested serializers require a custom `create`/`update` — prefer a flat write payload (PrimaryKey/`SlugRelatedField`) and nest only on read.

## Views: which flavor
- `@api_view(['GET','POST'])` — one-off functional endpoint, non-CRUD.
- `APIView` — full control, custom flow that isn't model-CRUD.
- **Generics** (`ListCreateAPIView`, `RetrieveUpdateDestroyAPIView`) — a single resource's CRUD.
- **`ModelViewSet` + a router** — the default for a full CRUD resource; least boilerplate, consistent URLs. Use `ViewSet` when you want the routing but custom actions. Reach for lower-level flavors only when the generic doesn't fit — don't hand-roll what a generic gives free.

## Permissions & queryset scoping
- Set `permission_classes` (`IsAuthenticated` at minimum); default via `DEFAULT_PERMISSION_CLASSES`. Never leave an endpoint `AllowAny` by omission.
- Object-level access → `has_object_permission`; it only runs for single-object lookups (`get_object`), **not** on list. So **also scope `get_queryset` per user** (`filter(owner=self.request.user)`). Scoping the queryset prevents leaks in lists AND turns unauthorized detail access into 404 — but don't rely on it as your only check; keep the permission class too.

## Authentication
- `SessionAuthentication` for a browser SPA on the same origin — **CSRF is enforced** for unsafe methods, so the client must send the CSRF token. `TokenAuthentication` (or JWT) for mobile/service clients — bearer credential, no CSRF.
- JWT via `djangorestframework-simplejwt` (not built in). Set `DEFAULT_AUTHENTICATION_CLASSES` deliberately; don't stack Session + Token without understanding the CSRF asymmetry.

## Pagination
- **Set `DEFAULT_PAGINATION_CLASS` + `PAGE_SIZE` globally.** An unbounded list endpoint is a footgun — one query can return the whole table. `PageNumberPagination` for UIs; `CursorPagination` for large/streaming or infinite-scroll (stable under writes).

## Throttling, filtering, versioning
- Throttling: `AnonRateThrottle`/`UserRateThrottle` via `DEFAULT_THROTTLE_CLASSES` + `DEFAULT_THROTTLE_RATES`; `ScopedRateThrottle` for expensive endpoints.
- Filtering: `django-filter` (`DjangoFilterBackend` + a `FilterSet`) over ad-hoc query-param parsing in `get_queryset`.
- Versioning: pick one scheme (`URLPathVersioning` is simplest) via `DEFAULT_VERSIONING_CLASS` before you have v2, not after.

## Browsable API
- Great in dev; in prod either drop `BrowsableAPIRenderer` from `DEFAULT_RENDERER_CLASSES` (leave `JSONRenderer` only) or gate it — it exposes forms and enumerates the API surface.

## Error handling
- DRF's default exception handler already yields a consistent shape from `APIException`/`ValidationError`. Raise those (or subclasses) rather than returning ad-hoc `Response(status=400)`. Wrap with a custom `EXCEPTION_HANDLER` only to reshape the envelope uniformly — keep it consistent across the API.

## Testing
- `APITestCase` + `APIClient` (`client.force_authenticate(user=...)` to skip the auth dance). Assert status codes and response JSON, not just 200. See `backend-testing.md`.

## The async caveat
- **DRF views are synchronous.** There is no async view/serializer support — do not `await` inside an `APIView`/`ViewSet` method or mark handlers `async def` expecting DRF to run them concurrently. If a route genuinely needs async I/O, use a plain **Django async view** (see `django.md`) or a separate async layer, and keep it outside DRF's view stack.
