<!--
library: redis
versions-covered: "redis-py 5.x–8.x (sync + asyncio)"
last-verified: 2026-07-12
provenance: auto-generated (pending review)
sources:
  - https://pypi.org/project/redis/
  - https://redis.readthedocs.io/en/stable/
  - https://github.com/redis/redis-py/releases
  - https://redis.io/docs/latest/develop/clients/redis-py/
-->

# Redis (redis-py) conventions

Python client idioms for Redis via the `redis` package (sync `redis.Redis` and async `redis.asyncio.Redis`) — caching, locks, pub/sub, streams, and Celery broker use. Load when `redis` appears in the manifest. Subordinate to project conventions — the project's existing client/pooling setup wins on conflict.

## Contents
- Version check
- Sync vs async client
- Connection pooling & `decode_responses`
- Data-structure idioms
- Expiry, cache-aside, locks
- Pipelines vs transactions
- Pub/sub vs streams
- SCAN not KEYS
- Lua / atomicity
- Resilience
- Celery, testing

## Version check (do this first)
- **`aioredis` is dead — do not install it.** It was merged into redis-py in **4.2** as `redis.asyncio`; import `from redis.asyncio import Redis`. A separate `aioredis` package is archived and conflicts.
- **The client API is stable across 4.x→8.x** — `Redis`, `ConnectionPool`, pipelines, and `redis.asyncio` look the same; upgrading is low-risk. Latest is **redis-py 8.0.1** (requires Python ≥3.10; 6.2+ needs 3.9+).
- **redis-py 8.0 defaults to RESP3 on the wire** but keeps legacy RESP2 Python response shapes, so existing code is unaffected. Pin `protocol=2` to force RESP2, or `legacy_responses=False` for unified shapes. Firm apps pin `redis>=5.0` — treat 5.x–8.x as one API surface.

## Sync vs async client
- Match the app's concurrency model. FastAPI async paths (`schwab_trader`) → `redis.asyncio.Redis`, `await` every call. Sync Django/Celery → `redis.Redis`.
- **Never call the sync client on an async event loop** — it blocks. Never share one client across both models.

## Connection pooling & decode_responses
- **Create one client (or pool) at startup and reuse it** — `redis.Redis` / `redis.asyncio.Redis` own a pool internally and are thread/task-safe. Prefer `Redis.from_url(url, ...)`.
- **Anti-pattern:** constructing a client (or `ConnectionPool`) per request/task — exhausts sockets and adds latency. Instantiate once, share via app state / a module singleton.
- `decode_responses=True` returns `str` instead of `bytes` — convenient, but breaks binary payloads (pickled Celery results, compressed blobs). Use it for text/JSON caches; leave it `False` where raw bytes matter. Be consistent per client.
- Async clients: `await client.aclose()` on shutdown.

## Data-structure idioms
- **String/counter:** `INCR`/`INCRBY` for atomic counters (never GET-then-SET). `SET` for opaque cache values (JSON-encode yourself).
- **Hash:** one object's fields under a key (`HSET user:1 name ... age ...`) — update fields without rewriting the whole value.
- **Set:** membership/dedup/tags (`SADD`, `SISMEMBER`); `SINTER`/`SUNION` for relations.
- **Sorted set:** leaderboards, rate windows, time-ordered indexes — score-ranked (`ZADD`, `ZRANGEBYSCORE`).
- **List:** simple queues (`LPUSH`/`BRPOP`) — but for durable work use Streams or a real broker.
- Pick by access pattern, not habit; a giant JSON string you re-serialize on every field write is the common smell.

## Expiry, cache-aside, locks
- **Cache-aside:** read key → miss → load from source → `SET key val EX <ttl>`. Always set a TTL; unbounded keys are a leak. Set TTL in the same `SET ... EX`, not a separate `EXPIRE` (race).
- **Locks:** naive `SET key val NX EX ttl` is a *best-effort* lock, not safe under failover/GC pauses — no fencing token. Use `redis.lock.Lock` (`client.lock(name, timeout=...)`, context manager, safe release via Lua token check) for single-instance; **Redlock across independent nodes** for stronger guarantees. Never `del` a lock you don't own.

## Pipelines vs transactions
- **Pipeline for round-trip batching:** `pipe = client.pipeline(transaction=False); pipe.set(...); pipe.get(...); pipe.execute()` — one network round-trip for many commands. Biggest easy win against chatty Redis code.
- **Transaction (`MULTI`/`EXEC`):** `pipeline(transaction=True)` — commands run atomically, but **no rollback** and no read-then-decide inside the block.
- **Optimistic locking with `WATCH`:** watch keys, read, then `MULTI`/`EXEC`; if a watched key changed, `execute()` raises `WatchError` — retry. This is the correct read-modify-write pattern.

## Pub/sub vs streams
- **Pub/sub is at-most-once, fire-and-forget** — messages published while a subscriber is down are lost, no history, no acks. Fine for cache invalidation / live fan-out, never for work that must not be dropped.
- **Streams are the durable alternative:** `XADD` appends; **consumer groups** (`XREADGROUP` + `XACK`) give at-least-once delivery, per-consumer offsets, and replay. Reach for streams (or a real broker) whenever loss is unacceptable.

## SCAN not KEYS
- **`KEYS` blocks the server** across the whole keyspace — never in production. Use `scan_iter(match=..., count=...)` (async: `async for k in client.scan_iter(...)`), which pages non-blockingly. Same for `HSCAN`/`SSCAN`/`ZSCAN`.

## Lua / atomicity
- For multi-step atomic ops (read-check-write) beyond `WATCH`, register a Lua script: `f = client.register_script(src)`; call `f(keys=[...], args=[...])`. Redis runs it atomically server-side, avoiding round-trips and races. redis-py handles `EVALSHA`/`EVAL` fallback.

## Resilience
- Set `socket_timeout` and `socket_connect_timeout` so a hung server doesn't stall callers. Enable `health_check_interval=30` to catch dropped idle connections.
- Configure retries: `retry=Retry(ExponentialBackoff(), 3)` with `retry_on_timeout=True` (or `retry_on_error=[...]`) — transient blips shouldn't surface as errors. Don't retry non-idempotent ops blindly.

## Celery, testing
- Redis as Celery broker/result backend (Django "Outgrown"): `redis://host:6379/0`. Keep broker DB separate from cache DB; results need a TTL (`result_expires`). Broker/serialization config belongs in `celery.md` — cross-reference it.
- **Testing:** `fakeredis` (with `aioredis`/async support) for fast unit tests without a server; use a **real ephemeral Redis** (container) for integration tests of pipelines, Lua, streams, and expiry, where fakeredis can diverge.
