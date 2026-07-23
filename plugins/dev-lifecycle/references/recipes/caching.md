<!--
recipe: caching
applies-to:
  - backend block: fastapi OR django (framework-neutral pattern; the Redis client idiom is the same either way)
last-verified: 2026-07-23
provenance: manual
sources:
  - https://redis.readthedocs.io/en/stable/
  - references/backend/redis.md
  - references/security/data-protection.md
  - references/backend/postgres.md
-->

# Caching (Redis cache-aside)

Wire response/query caching with Redis using the cache-aside pattern: read-through on a miss, an explicit TTL on every key, invalidation on write, and a key-naming discipline that keeps a shared cache from ever leaking one user's authorized data to another. Everything here is **subordinate to the project's existing conventions** — when they conflict, the project wins.

## Contents
- What this wires
- Prerequisites
- Wire-up steps
- Cache key discipline (read this before adding a key)
- Invalidation on write
- What NOT to cache in a shared key
- Doc fragment

## What this wires
Applying this recipe gives a feature working read-through caching: an expensive or frequently-read query result (or response body) is looked up in Redis first, computed and stored on a miss, served straight from Redis on a hit, and explicitly evicted the moment the underlying data changes — never left to a TTL alone to eventually converge.

It **composes an existing piece** — it invents no new infrastructure:
- **`references/backend/redis.md`** — the kit's Redis (redis-py) convention doc this recipe wires directly: "Expiry, cache-aside, locks" is the canonical cache-aside pattern this recipe applies (`SET key val EX <ttl>` in one call, never a separate `EXPIRE`), "Connection pooling" for how the client is constructed once and reused, and "Sync vs async client" for matching the app's own concurrency model (`redis.asyncio.Redis` for an async FastAPI app, `redis.Redis` for sync Django).
- **`references/security/data-protection.md`**'s data-classification discipline — the same "public / internal / sensitive / restricted" classification that governs storage governs caching too: a cache entry is a second copy of the data, subject to the same rules the primary store already follows (see "What NOT to cache" below).

## Prerequisites
- A Redis instance reachable from the app — the same instance a project's Celery broker (`background-jobs` recipe) or WebSocket fan-out (`realtime-websockets` recipe) may already use, **on a separate DB number** from either (per `redis.md`'s "Celery, testing" section: keep the broker DB and the cache DB distinct).
- `redis` (redis-py) as a dependency — no dedicated compatibility-matrix row exists for it yet; pin against `redis.md`'s own "Version check" section (redis-py 5.x–8.x is treated as one stable API surface) at implementation time.
- A client constructed **once at startup and reused** (`Redis.from_url(url, ...)`, held in app state or a module singleton) — never a client built per request/task, per `redis.md`'s explicit anti-pattern.

## Wire-up steps
1. **Construct one Redis client at startup**, matching the app's concurrency model: `redis.asyncio.Redis` (awaited on every call) for an async FastAPI app, `redis.Redis` for sync Django — never the sync client from an async event loop, per `redis.md`'s "Sync vs async client." Set `socket_timeout`/`socket_connect_timeout` and `health_check_interval=30` (per `redis.md`'s "Resilience") so a hung or dropped Redis connection surfaces as a bounded failure, not a stalled request.
2. **Read cache-aside on the hot path**: check the key, and only compute + write on a miss.
   ```python
   async def get_widget(widget_id: str) -> WidgetOut:
       key = f"widget:v1:{widget_id}"
       cached = await redis.get(key)
       if cached is not None:
           return WidgetOut.model_validate_json(cached)
       widget = await repo.get(widget_id)   # the real source of truth
       out = WidgetOut.model_validate(widget)
       await redis.set(key, out.model_dump_json(), ex=300)  # TTL in the same call — see step 3
       return out
   ```
3. **Always set the TTL in the same `SET`/`SETEX` call, never a separate `EXPIRE` afterward** — per `redis.md`'s "Expiry, cache-aside, locks": a separate `EXPIRE` call races the read path (a reader could observe the key before its expiry is applied) and, if the process dies between the two calls, leaves an unbounded key behind. Every cached key gets an explicit TTL; there is no such thing as a cache key with no expiry in this pattern.
4. **Pick a TTL from the data's actual staleness tolerance, not a single global default.** A public catalog listing that's fine 60 seconds stale is a different TTL than a per-request rate-limit counter; don't copy one TTL constant across every cache call site without asking how stale is actually acceptable for that specific value.
5. **Invalidate explicitly on write** — see "Invalidation on write" below; a TTL is a bound on staleness, not a substitute for invalidating a key the moment the data it holds actually changes.

## Cache key discipline (read this before adding a key)
- **Namespace every key with an entity type and a version prefix**: `widget:v1:{id}`, never a bare `{id}` — the version segment (`v1`) lets a schema/shape change invalidate every existing entry at once (bump to `v2`) instead of writing a one-off migration against live cache data, which Redis has no query language to do safely anyway.
- **A shared/global cache key names its scope explicitly**: `widgets:list:v1:category={category}` for a category-scoped list, not a single key `widgets:list` covering every possible query shape — an ungoverned key that silently means "whatever the last caller's filters were" is a correctness bug waiting to surface as one user seeing another's filtered results.
- **Never build a key from unsanitized user input directly** — a key built from a raw free-text search string, unbounded, is both a minor injection-adjacent surface (Redis key names aren't a security boundary the way SQL is, but an unbounded key space is still a resource-exhaustion vector) and a cache-hit-rate killer (every trivially different input string misses). Hash or normalize free-text input before it becomes part of a key.

## Invalidation on write
- **Delete (or overwrite) the exact key(s) a write affects, in the same transaction/request that performs the write** — don't rely on the next read's TTL expiry to eventually pick up the change. A write path that updates `widgets` but never touches `widget:v1:{id}` leaves stale data being served for up to the full TTL.
  ```python
  async def update_widget(widget_id: str, payload: WidgetUpdate) -> WidgetOut:
      widget = await repo.update(widget_id, **payload.model_dump(exclude_unset=True))
      await redis.delete(f"widget:v1:{widget_id}")   # invalidate the single-item cache
      await redis.delete(f"widgets:list:v1:*")        # see note below — SCAN, not a literal glob DELETE
      return WidgetOut.model_validate(widget)
  ```
- **A write that could be cached under multiple derived keys (a list, a filtered view) needs every one of them invalidated** — this is the actual hard part of cache invalidation. Two common strategies: (a) keep the derived-key set small and enumerable (a fixed set of category/page combinations) so a write can delete them explicitly; (b) give derived/list keys a **short** TTL (seconds, not minutes) so a missed invalidation self-heals quickly instead of staying wrong for a long window — list/aggregate views generally tolerate a shorter TTL than a single-item lookup does.
- **`redis.md`'s `KEYS` warning applies to invalidation too**: never `KEYS widgets:list:*` then `DELETE` each match in a request path — `KEYS` blocks the server across the whole keyspace. Use `scan_iter(match=...)` if a pattern-based sweep is genuinely needed, and prefer it as an out-of-band maintenance operation, not something a single write request triggers synchronously.

## What NOT to cache in a shared key
This is the failure mode this recipe exists to prevent: **never cache per-user or per-authorization-scope data under a key that doesn't encode the acting principal, and never serve a cached value to a request without first confirming that principal is still authorized to see it.**
- **A key must encode the authorization scope it's valid for.** `user:{user_id}:notifications:v1` is safe — the key itself scopes the cached value to one user. `notifications:v1` (no user segment) cached with "whichever user's request happened to populate it" is the exact bug: the next different user's request hits the same key and receives someone else's data.
- **Don't cache a rendered response that embeds a specific caller's authorization state** (their role, their permitted fields, a personalized filter) under a key shared across callers — even if the underlying *data* is the same for everyone, a response shaped differently per role/permission needs either a key that encodes the role/permission, or must not be cached as a rendered whole (cache the underlying data, apply the per-caller shaping after the cache read).
- **Restricted-tier data** (per `references/security/data-protection.md`'s classification: payment data, government IDs, health data) generally shouldn't be cached at all, independent of key-scoping — a cache entry is a second, less-access-controlled-by-default copy of the data (Redis itself typically has weaker per-record ACLs than the primary DB's row-level authorization), and it now has its own TTL-governed lifetime to reason about for retention/deletion purposes. If a restricted-tier value's read latency genuinely needs caching, that is a deliberate, reviewed decision — not this recipe's default.
- **A 404/403 response is also cacheable state that must be scoped correctly** — don't cache "this resource doesn't exist" or "you're not allowed" under a key that a *different* user's identical-looking request would also hit; the answer to "can I see this" is itself per-principal.

## Doc fragment
The portable fragment this recipe contributes to the project's root README when applied:

```markdown
### Caching (Redis cache-aside)
- **Setup:** Hot reads go through cache-aside against Redis: check `{entity}:v{n}:{id}` first, compute and `SET ... EX <ttl>` on a miss, serve straight from cache on a hit. TTL is always set in the same `SET` call, never a separate `EXPIRE`. Writes explicitly delete the keys they affect rather than waiting for TTL expiry. See `references/backend/redis.md`.
- **Secrets:** none new — reuses the project's existing Redis instance (on its own DB number, separate from any Celery broker/WS pub-sub DB).
- **Maintenance:** Every cache key that scopes to a specific user/authorization context must encode that scope in the key itself (`user:{user_id}:...`) — never share a key across callers with different authorization outcomes. Restricted-tier data (payment/health/government-ID) is not cached by default. Bump a key's version segment (`v1` → `v2`) rather than trying to migrate live cache data on a shape change.
```

---
<!--
Recipe authored via the `recipe-author` skill (Stage 11, #34, batch 2). Wires
references/backend/redis.md's own "Expiry, cache-aside, locks" section
directly — no new caching infrastructure invented. The authorization-scoping
discipline in "What NOT to cache in a shared key" is this recipe's own
security-critical section, cross-referencing references/security/
data-protection.md's classification model rather than restating it.
-->
