<!--
recipe: search
applies-to:
  - backend block: fastapi (SQLAlchemy 2.0.x + `postgresql` dialect TSVECTOR) OR django (`django.contrib.postgres.search` — same Postgres FTS underneath)
last-verified: 2026-07-23
provenance: manual
sources:
  - https://www.postgresql.org/docs/current/textsearch.html
  - https://docs.djangoproject.com/en/5.2/ref/contrib/postgres/search/
  - https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#full-text-search
  - references/backend/postgres.md
  - references/backend/sqlalchemy.md
-->

# Search (Postgres full-text search)

Wire full-text search using PostgreSQL's built-in `tsvector`/`tsquery` machinery and a GIN index — the kit-native default that adds no new infrastructure — wired to an existing model and the existing `Page[T]` pagination envelope. Everything here is **subordinate to the project's existing conventions** — when they conflict, the project wins.

## Contents
- What this wires
- Prerequisites
- Wire-up steps (FastAPI / SQLAlchemy)
- Wire-up steps (Django / DRF)
- Ranking and "search as you type"
- When to graduate to a dedicated search engine
- Doc fragment

## What this wires
Applying this recipe gives a searchable text field (a title, a body, a combination of columns) a real full-text query path: a generated/maintained `tsvector` column, a GIN index on it (per `references/backend/postgres.md`'s own "Indexing" section: "GIN for jsonb/full-text/arrays"), and a search endpoint that runs a `to_tsquery`/`plainto_tsquery` match through the existing pagination envelope — no new database, no new service, no new dependency beyond what's already in the compatibility matrix (Postgres + SQLAlchemy/Django are already pinned there).

It **composes existing pieces** — it invents no new infrastructure:
- **`references/backend/postgres.md`**'s "Indexing" section — the GIN-index guidance this recipe applies specifically to a `tsvector` column, and its "Performance" section's `EXPLAIN (ANALYZE, BUFFERS)` discipline for confirming the index is actually used rather than a sequential scan.
- **`references/backend/sqlalchemy.md`**'s `select()`-style 2.0 query pattern — a search query is an ordinary `select()` with a `tsvector @@ tsquery` predicate, built and executed the same way every other filtered query in the app already is.
- **`templates/components/backend/pagination/`**'s `Page[T]`/`PageParams`/`paginate_select` — a search result list is a paginated list like any other; this recipe wires the search predicate into the `select()` passed to `paginate_select`, it does not invent a second pagination shape for search results.
- **An existing model** (e.g. `app/models/blog_post.py`'s `BlogPost` — `title`/`body_html`, already in the kit's own worked FastAPI backend — or any project model with searchable text columns) — this recipe adds a `tsvector` column and index to an existing table, it does not stand up a new one.

## Prerequisites
- **PostgreSQL** (matrix: **18.x**) — Postgres FTS is a Postgres-specific feature; this recipe does not have a sqlite-compatible fallback (unlike `pagination`'s deliberately dialect-neutral `paginate_select`, which the search predicate layers on top of, not replaces). A project on the FastAPI track that runs its hermetic test suite against sqlite (per `pagination/README.md`'s own dual-dialect note) needs a Postgres-backed integration test specifically for the search predicate — a sqlite `tsvector`-free unit test cannot exercise it.
- A backend block with the `pagination` catalog component vendored (ships by default).
- Django track: `'django.contrib.postgres'` in `INSTALLED_APPS` (ships with Django, no extra dependency) to use `SearchVectorField`/`SearchVector`/`SearchQuery`.

## Wire-up steps (FastAPI / SQLAlchemy)
1. **Add a `tsvector` column to the model**, using SQLAlchemy's Postgres-dialect `TSVECTOR` type:
   ```python
   from sqlalchemy.dialects.postgresql import TSVECTOR
   from sqlalchemy import Computed

   class BlogPost(Base, UUIDPrimaryKey, TimestampMixin, SoftDeleteMixin):
       ...
       search_vector: Mapped[str] = mapped_column(
           TSVECTOR,
           Computed("to_tsvector('english', coalesce(title, '') || ' ' || coalesce(body_html, ''))", persisted=True),
       )
   ```
   A **generated column** (`Computed(..., persisted=True)`, Postgres 12+) keeps the `tsvector` in sync with the source columns automatically on every insert/update — no application-code responsibility to remember to recompute it, and no drift between the searchable text and what's actually indexed. This is the preferred default over a manually-maintained column (an app-level "update the tsvector on save" hook) precisely because it can't be forgotten.
2. **Add the GIN index in the same migration**:
   ```python
   op.create_index("ix_blog_posts_search_vector", "blog_posts", ["search_vector"], postgresql_using="gin")
   ```
3. **Build the search query as an ordinary `select()`**, predicate via the `@@` match operator, and run it through the existing pagination component exactly as any other list endpoint does:
   ```python
   from sqlalchemy import func, select

   async def search_blog_posts(query: str, params: PageParams, session: AsyncSession) -> Page[BlogPostOut]:
       tsquery = func.plainto_tsquery("english", query)
       stmt = (
           select(BlogPost)
           .where(BlogPost.search_vector.op("@@")(tsquery))
           .where(BlogPost.deleted_at.is_(None))
           .order_by(func.ts_rank(BlogPost.search_vector, tsquery).desc())
       )
       result = await paginate_select(session, stmt, params)
       mapped = [BlogPostOut.model_validate(p) for p in result.items]
       return Page.create(mapped, total=result.total, params=params)
   ```
   `plainto_tsquery` (not `to_tsquery`) accepts plain user-typed text without requiring the caller to know `tsquery`'s own boolean operator syntax (`&`, `|`, `<->`) — use `to_tsquery`/`websearch_to_tsquery` only when the endpoint deliberately exposes that operator syntax to the caller.
4. **Verify the index is actually used**, per `postgres.md`'s "Performance" section: `EXPLAIN (ANALYZE, BUFFERS)` the search query and confirm a `Bitmap Index Scan` on the GIN index rather than a sequential scan — a `to_tsvector(...)` call inline in the `WHERE` clause against a column with no matching generated/indexed `tsvector` silently falls back to a full-table recompute-and-scan on every query, which looks correct but never uses the index.

## Wire-up steps (Django / DRF)
1. **Add a `SearchVectorField`** (from `django.contrib.postgres.search`) to the model, populated the same generated-column way via a migration's raw SQL `Computed`-equivalent (Django doesn't wrap Postgres generated columns natively as of 5.2 — use `django.contrib.postgres.indexes.GinIndex` plus a `RunSQL` migration operation adding the generated column, or, if the project prefers Django's own idiom, a `SearchVectorField` populated by a `pre_save`/signal-based `SearchVector(...)` update — the generated-column approach above is preferred for the same "can't be forgotten" reason).
2. **Index it**: `GinIndex(fields=["search_vector"])` in the model's `Meta.indexes` — mirrors the SQLAlchemy `postgresql_using="gin"` index above.
3. **Query with `SearchQuery`/`SearchRank`**, run through the project's existing DRF pagination class (the same `PageNumberPagination` shape `pagination/README.md`'s "DRF parity" note already documents this kit's Django track reimplementing):
   ```python
   from django.contrib.postgres.search import SearchQuery, SearchRank

   def search_view(request):
       query = SearchQuery(request.query_params.get("q", ""), search_type="plain")
       qs = (
           BlogPost.objects.filter(search_vector=query, deleted_at__isnull=True)
           .annotate(rank=SearchRank("search_vector", query))
           .order_by("-rank")
       )
       # paginated the same way every other DRF list view already is
   ```

## Ranking and "search as you type"
- **`ts_rank`/`SearchRank`** orders results by textual relevance (term frequency/position) — always order search results by rank, not by an unrelated column like `created_at`, or the "best match" experience degrades to "most recent match."
- **This recipe is not a typeahead/autocomplete solution.** `tsquery` matching is whole-word (with stemming), not prefix matching — a query for `"widg"` will not match `"widget"` under `plainto_tsquery`. Postgres supports prefix matching via `to_tsquery('widg:*')`, usable for a genuine "search as you type" UI, but treat it as a deliberate, separate query mode from the whole-word default above, not a drop-in replacement — prefix queries also can't use a plain GIN `tsvector` index as efficiently at high query volume without additional tuning (out of scope here).

## When to graduate to a dedicated search engine
Postgres FTS is the right default at this kit's target scale — no new infrastructure, transactionally consistent with the data it indexes (a generated column can never drift), and good enough for most projects' actual search volume and relevance needs. Reach for a dedicated engine (Elasticsearch/OpenSearch/Meilisearch/Algolia) only when the project genuinely needs one or more of: relevance tuning beyond `ts_rank` (custom scoring, synonyms, typo tolerance/fuzzy matching at scale), faceted search/aggregations across large result sets, sub-100ms search latency at a scale where Postgres's own query planner and index maintenance start to strain, or search volume high enough to want it isolated from the primary transactional database's load. That is a **project-level infrastructure decision** (a new service, a new compatibility-matrix row, a sync pipeline keeping the external index consistent with Postgres) — this recipe's Postgres-native path is deliberately the starting point, not a permanent ceiling.

## Doc fragment
The portable fragment this recipe contributes to the project's root README when applied:

```markdown
### Search (Postgres full-text)
- **Setup:** Searchable models carry a generated `tsvector` column (`to_tsvector(...)`, kept in sync automatically — no app code updates it) with a GIN index. The search endpoint runs a `plainto_tsquery` match through the existing `Page[T]` pagination, ordered by `ts_rank`. See `references/backend/postgres.md`'s "Indexing" section.
- **Secrets:** none — built entirely on the existing Postgres database, no new service.
- **Maintenance:** Confirm the GIN index is actually used (`EXPLAIN (ANALYZE, BUFFERS)`, expect a Bitmap Index Scan) whenever the search predicate changes. Graduate to a dedicated search engine only when relevance tuning, faceting, or scale genuinely outgrow Postgres FTS — not by default.
```

---
<!--
Recipe authored via the `recipe-author` skill (Stage 11, #34, batch 2). Wires
references/backend/postgres.md's GIN-index guidance and the existing
pagination component's Page[T]/paginate_select directly — no new search
infrastructure. A generated `tsvector` column is used over a manually
maintained one specifically because it can't silently drift from its source
columns, the same "can't be forgotten" reasoning batch 1's payments recipe
applies to server-decided amounts. The "graduate to a dedicated engine"
section is scoped as a deliberate future project decision, not a kit gap.
-->
