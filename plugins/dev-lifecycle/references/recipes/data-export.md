<!--
recipe: data-export
applies-to:
  - backend block: fastapi (`StreamingResponse`) OR django (`StreamingHttpResponse`) — same streamed-CSV pattern, framework-specific response type
last-verified: 2026-07-23
provenance: manual
sources:
  - https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse
  - https://docs.djangoproject.com/en/5.2/howto/outputting-csv/
  - references/security/data-protection.md
  - references/backend/postgres.md
  - templates/components/backend/pagination/README.md
-->

# Data export (CSV / report)

Wire a CSV/report export endpoint that streams rows as they're generated rather than building the whole file in memory, reuses the same filtered query a list endpoint already runs, pushes filtering/formatting work into the database rather than pulling every row into Python first, and enforces the same authorization scoping the underlying list endpoint already has — so an export can never leak across a tenant/user boundary a paginated list view already respects. Everything here is **subordinate to the project's existing conventions** — when they conflict, the project wins.

## Contents
- What this wires
- Prerequisites
- Wire-up steps (FastAPI)
- Wire-up steps (Django)
- Do the work in the database, not in Python
- Access control: no cross-tenant/cross-user leak
- Doc fragment

## What this wires
Applying this recipe gives a feature a working export path: a caller requests a CSV (or similar tabular format) of a filtered, authorization-scoped set of records, the server streams rows to the response as it reads them from the database — never materializing the full result set (and never the full output file) in memory at once — and the export is subject to exactly the same access control the equivalent paginated list endpoint already enforces.

It **composes existing pieces** — it invents no new infrastructure:
- **The same query a paginated list endpoint already builds** — an export is that identical `select()`/`QuerySet` (same `WHERE`/authorization filters), with `LIMIT`/`OFFSET` removed and the result iterated instead of paginated. Reuse the query-building function a list endpoint already has; don't hand-write a second, divergent query for export that could drift from the list endpoint's own filtering/authorization logic.
- **`templates/components/backend/pagination/`**'s pattern of building the filtered `select()`/`QuerySet` once and applying pagination as a final step — the same "build the filtered statement, then decide how to consume it" shape this recipe reuses, substituting a streaming iterator for `paginate_select`'s `LIMIT`/`OFFSET`.
- **`references/security/data-protection.md`**'s "Access control & logging" section — its explicit "Bulk export/download paths for sensitive data are a common gap — audit them the same as individual-record access, and rate-limit them" is this recipe's own authorization discipline, applied directly.
- **The `audit-logging` recipe** — an export of restricted/sensitive-tier data is exactly the "access to or export of restricted-tier data" case that recipe's "What to audit" section already names; wire `audit_event("export.<entity>", actor=..., resource=f"export:{entity}:{filter_summary}", outcome="success", row_count=...)` at the export's completion.

## Prerequisites
- A backend block with an existing filtered list endpoint (or its underlying query-building function) for the entity being exported — this recipe reuses it rather than building export-specific filtering from scratch.
- No new dependency: `StreamingResponse` (FastAPI/Starlette) and `StreamingHttpResponse` (Django) ship with the framework; Python's stdlib `csv` module (via a small generator wrapper — see step 2 below) needs no external CSV library for the common case.

## Wire-up steps (FastAPI)
1. **Reuse the list endpoint's query-building function**, stripped of `LIMIT`/`OFFSET`: if `list_widgets` builds `stmt = select(Widget).where(...)` before handing it to `paginate_select`, the export endpoint calls that same statement-building function and iterates the *unpaginated* `stmt` directly instead.
2. **Stream rows with an async generator, writing CSV incrementally** — never `csv.writer` into an in-memory `StringIO` for the whole result set, and never `.all()` the query before iterating:
   ```python
   import csv
   import io
   from fastapi.responses import StreamingResponse

   async def export_widgets(filters: WidgetFilters, db: AsyncSession = Depends(get_db)) -> StreamingResponse:
       stmt = build_widget_query(filters)   # the SAME filtered statement list_widgets uses, no LIMIT/OFFSET

       async def rows() -> AsyncIterator[str]:
           buf = io.StringIO()
           writer = csv.writer(buf)
           writer.writerow(["id", "name", "created_at"])   # header
           yield buf.getvalue()
           buf.seek(0); buf.truncate(0)
           # server_side_cursors / yield_per keeps this from loading the whole
           # result set into memory even though the DB call itself is one query
           async for widget in await db.stream_scalars(stmt):
               writer.writerow([widget.id, widget.name, widget.created_at.isoformat()])
               yield buf.getvalue()
               buf.seek(0); buf.truncate(0)

       return StreamingResponse(rows(), media_type="text/csv", headers={
           "Content-Disposition": 'attachment; filename="widgets.csv"',
       })
   ```
   `db.stream_scalars(stmt)` (SQLAlchemy 2.0's async streaming execution) fetches rows from the database in batches as the generator is consumed, rather than the driver buffering the entire result set — the actual mechanism that keeps memory bounded regardless of export size.
3. **Set `Content-Disposition: attachment`** with an explicit filename so the browser downloads rather than renders the CSV inline, and `media_type="text/csv"`.

## Wire-up steps (Django)
1. **Reuse the list view's `QuerySet`-building function**, without its pagination step.
2. **Stream with `StreamingHttpResponse` and Django's own `Echo`-writer pattern** (per Django's "Outputting CSV" how-to — a pseudo-file object whose `write()` just returns what it's given, fed to `csv.writer`, iterated lazily over the `QuerySet`):
   ```python
   import csv
   from django.http import StreamingHttpResponse

   class Echo:
       def write(self, value):
           return value

   def export_widgets(request):
       qs = build_widget_queryset(request)  # the SAME filtered queryset the list view uses
       writer = csv.writer(Echo())

       def rows():
           yield writer.writerow(["id", "name", "created_at"])
           for widget in qs.iterator(chunk_size=2000):   # server-side chunked fetch, not one big list()
               yield writer.writerow([widget.id, widget.name, widget.created_at.isoformat()])

       response = StreamingHttpResponse(rows(), content_type="text/csv")
       response["Content-Disposition"] = 'attachment; filename="widgets.csv"'
       return response
   ```
   `QuerySet.iterator(chunk_size=...)` is Django's own equivalent to step 2's `stream_scalars` — it fetches from the database in chunks rather than evaluating the whole `QuerySet` into a list, which is what a plain `for widget in qs:` on an unpaginated queryset would otherwise do.

## Do the work in the database, not in Python
- **Filter, sort, and aggregate in the query, not after fetching.** An export that runs `SELECT *` unfiltered and then filters/sorts/summarizes in a Python loop both defeats indexing (per `references/backend/postgres.md`'s "Performance" section) and is the exact shape that forces loading everything into memory to begin with. Push every `WHERE`/`ORDER BY`/aggregate the export needs into the `select()`/`QuerySet`.
- **Compute derived/summary columns in SQL where practical** (a `SUM`/`COUNT`/window function) rather than accumulating totals in the Python generator — keeps the export's Python-side work to "format this row," not "compute this report," and keeps memory use flat regardless of row count.
- **A report that's genuinely a heavy aggregate query** (not a row-by-row export) still benefits from the same principle: let Postgres do the aggregation via `GROUP BY`/window functions, and stream the (typically much smaller) aggregated result set the same way.

## Access control: no cross-tenant/cross-user leak
This is the failure mode this recipe exists to prevent, per `references/security/data-protection.md`'s explicit callout that bulk export is "a common gap":
- **The export endpoint applies the exact same authorization filter the list endpoint applies — not a superset.** If `list_widgets` scopes to `WHERE tenant_id = :caller_tenant_id` (or an ownership/role check), `export_widgets` must build its query through the identical filtering function, not a hand-copied version that's easy to let drift out of sync as the list endpoint's authorization logic evolves. Reusing the same query-building function (steps above) is what keeps this true structurally, not just by convention.
- **Never accept a `tenant_id`/`user_id`/scope filter from the request body or query string as the sole source of truth for what's exported.** The authenticated caller's own identity (from the resolved principal) determines the export's scope; a client-supplied scope parameter, if the endpoint takes one at all, may only **narrow** what the caller's own authorization already permits — never widen it.
- **Rate-limit and audit bulk export the same as any other access to the data it covers** — per `data-protection.md`'s explicit instruction. A single unrated export endpoint is a much larger data-exfiltration surface per request than the paginated list view it mirrors (one call can walk the entire authorized scope), so both the rate limit and the audit trail matter more here, not less, than on the equivalent list endpoint.
- **Restricted-tier data** (per `data-protection.md`'s classification) exported in bulk deserves the same scrutiny as storing it — confirm the export doesn't include a column the individual-record view itself would withhold (a field visible in a detail view for legitimate reasons doesn't automatically belong in a bulk CSV handed to the same caller).

## Doc fragment
The portable fragment this recipe contributes to the project's root README when applied:

```markdown
### Data export (CSV)
- **Setup:** Export endpoints reuse the same filtered, authorization-scoped query a list endpoint already builds (no separate, divergent export query) and stream rows to the response (`StreamingResponse`/`db.stream_scalars` on FastAPI; `StreamingHttpResponse`/`QuerySet.iterator()` on Django) rather than building the file in memory. Filtering/sorting/aggregation happens in the database query, not in a Python loop after fetching.
- **Secrets:** none new.
- **Maintenance:** Bulk export is rate-limited and audited the same as individual-record access to the data it covers (`references/security/data-protection.md`) — a bigger exfiltration surface per request than the list view it mirrors. The export's authorization scope always comes from the authenticated caller, never a client-supplied parameter alone.
```

---
<!--
Recipe authored via the `recipe-author` skill (Stage 11, #34, batch 2). Wires
FastAPI's/Django's own streaming-response mechanisms, the existing
pagination component's "build the filtered statement once" shape, and
references/security/data-protection.md's explicit "bulk export is a common
gap — audit and rate-limit it" instruction, applied directly rather than
restated abstractly. The access-control section's core rule — reuse the
list endpoint's own query-building function rather than a hand-copied
export query — is this recipe's structural fix for the cross-tenant-leak
failure mode, not just a documented convention.
-->
