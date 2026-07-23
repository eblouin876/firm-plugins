<!--
recipe: background-jobs
applies-to:
  - backend block: django (Celery + Redis broker — references/backend/celery.md's own reference stack) OR fastapi (BackgroundTasks for light fire-and-forget work; a real task queue is a project addition — see "What the kit does not provide")
last-verified: 2026-07-23
provenance: manual
sources:
  - https://docs.celeryq.dev/en/stable/userguide/tasks.html
  - https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html
  - https://fastapi.tiangolo.com/tutorial/background-tasks/
  - references/backend/celery.md
  - references/backend/fastapi.md
  - references/backend/redis.md
-->

# Background jobs

Wire asynchronous task/worker execution so a request never blocks on slow, retryable, or scheduled work: Celery + Redis on the Django track (the kit's real, documented task-queue stack), and FastAPI's native `BackgroundTasks` for light fire-and-forget work on that track — with an explicit, honest note on what a heavier FastAPI workload needs that the kit does not yet ship. Everything here is **subordinate to the project's existing conventions** — when they conflict, the project wins.

## Contents
- What this wires
- Prerequisites
- Wire-up steps (Django + Celery)
- Wire-up steps (FastAPI + BackgroundTasks)
- What the kit does not provide (be honest about the FastAPI gap)
- Idempotent tasks, retries, and not blocking the request
- Doc fragment

## What this wires
Applying this recipe gives a feature working background execution appropriate to its backend track: on Django, a `@shared_task` running on a Celery worker against the same Redis instance already available to the project (see `references/backend/redis.md`), callable with `.delay()`/`.apply_async()` and, where needed, scheduled via `django-celery-beat`. On FastAPI, `BackgroundTasks` for light, non-critical, in-process work that must not block the response.

It **composes existing pieces**:
- **`references/backend/celery.md`** — the kit's real, current Celery convention doc (Celery 5.6.x + django-celery-beat 2.9.0): app setup/autodiscovery, `@shared_task` vs `@app.task`, `.delay()`/`.apply_async()`, `acks_late`/idempotency, declarative retries with backoff, routing/queues, periodic tasks, worker concurrency, and serialization security. This recipe wires a project's own tasks to it; it does not restate its content.
- **`references/backend/redis.md`** — the broker (and optional result backend) Celery runs against; also the pattern for a project's own Redis client if a task needs one directly (cache-aside, locks, pub/sub) beyond the Celery broker connection itself.
- **`references/backend/fastapi.md`**'s "Background work" section — the FastAPI track's own guidance: `BackgroundTasks` for light work, "the project's task queue (Celery/arq/taskiq)" for heavier work, without picking one for FastAPI. This recipe follows that same split rather than inventing a FastAPI task-queue convention the kit doesn't have.
- **The `idempotency` catalog component** (`templates/components/security/idempotency/`) — not itself a task-queue mechanism, but the same idempotency discipline (a stable operation key, safe replay) that makes a task safe to retry; see "Idempotent tasks" below for how the same principle applies inside a task body, not just at the HTTP boundary.

## Prerequisites
- **Django track:** a backend block (`templates/backend/django`) with `celery`/`django-celery-beat` added to the project's dependencies (no compatibility-matrix row exists for Celery yet — `references/backend/celery.md`'s own "Version check" section is the version source: Celery 5.6.x, django-celery-beat 2.9.0 as of this recipe's `last-verified`; re-verify against PyPI before pinning at implementation time) and a Redis instance reachable at `CELERY_BROKER_URL`.
- **FastAPI track:** no new dependency — `BackgroundTasks` ships with FastAPI itself. A heavier task queue (arq, Dramatiq, or Celery adapted to run under `asyncio`) is a **project addition**, not something this kit vendors — see "What the kit does not provide."
- A Redis instance for the Django track's broker (and, optionally, a separate DB index as the result backend) — per `references/backend/redis.md`'s "Celery, testing" section: keep the broker DB and any app-level cache DB distinct.

## Wire-up steps (Django + Celery)
1. **Wire the Celery app per `references/backend/celery.md`'s "App setup & autodiscovery."** `proj/celery.py` builds the `Celery('proj')` instance, calls `app.config_from_object('django.conf:settings', namespace='CELERY')`, and `app.autodiscover_tasks()`; import it in `proj/__init__.py` so `@shared_task` binds at startup. Config keys are lowercase (`CELERY_BROKER_URL` in settings maps to `broker_url`) — don't emit the legacy uppercase form.
2. **Set `CELERY_BROKER_URL` (and, only if a task's return value is actually consumed, `CELERY_RESULT_BACKEND`) as environment config**, resolved the same way every other runtime setting in the block is (the block's own settings module) — never hardcoded in `celery.py`. Point both at the project's Redis instance, on separate DB numbers if both are used (`redis://redis:6379/0` broker, `/1` result backend), per `celery.md`'s "Broker vs result backend."
3. **Define each task with `@shared_task`, not `@app.task`** — per `celery.md`'s "Defining tasks," `@shared_task` doesn't bind to a specific app instance, so a reusable `tasks.py` works without importing the Celery app (avoids circular imports). Pass **IDs, not ORM objects** as task arguments (`celery.md`'s "Pitfalls & testing") — an ORM object serializes stale and bloats the message; re-fetch inside the task.
4. **Call tasks with `.delay()` or `.apply_async()`** from the view/serializer that triggers the work — never call the task function directly (that runs it in-process, synchronously, defeating the entire point). Use `.apply_async(..., queue=..., countdown=..., eta=...)` when a specific queue, delay, or scheduling is needed.
5. **Isolate slow/IO-heavy tasks onto their own queue** (`celery.md`'s "Routing & queues": `task_routes = {'app.tasks.slow_thing': {'queue': 'io'}}`) with a dedicated worker (`celery -A proj worker -Q io`) so a burst of slow tasks can't starve fast ones on the default queue.
6. **For scheduled/periodic work, use `django-celery-beat`'s DB-backed scheduler**, not a hardcoded cron-like schedule — add `django_celery_beat` to `INSTALLED_APPS`, migrate, and run **exactly one** `beat` process (`celery -A proj beat -l INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler`) separate from the worker process(es). Two `beat` processes double-fire every scheduled task — this is an operational invariant to enforce at the deploy-configuration layer (one replica, not autoscaled), not something Celery itself guards against.
7. **Keep `task_serializer`/`accept_content` at `json`** (the default) — per `celery.md`'s "Serialization & security," never accept `pickle` from an untrusted broker; it executes arbitrary code on deserialize.

## Wire-up steps (FastAPI + BackgroundTasks)
1. **Reach for `BackgroundTasks` only for light, fire-and-forget work tied to one request** — per `references/backend/fastapi.md`'s "Background work" section: e.g. sending a notification email after a response, writing a non-critical audit-adjacent log line. Add the parameter to the route handler and schedule the callable; it runs after the response is sent, in the same process.
   ```python
   from fastapi import BackgroundTasks

   @router.post("/widgets")
   async def create_widget(payload: WidgetCreate, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)) -> WidgetOut:
       widget = await repo.create(**payload.model_dump())
       background_tasks.add_task(notify_widget_created, widget.id)
       return WidgetOut.model_validate(widget)
   ```
2. **Know the limits before reaching for it on anything heavier.** `BackgroundTasks` runs **in-process**, with no retry, no persistence, and no cross-process durability — a worker restart or crash between "response sent" and "task finished" silently drops the work, and there is no dashboard, dead-letter handling, or backoff. It is the right tool for "best-effort, cheap, and it's fine if it's occasionally lost" — never for anything the project cannot afford to silently lose (payment follow-up, an irreversible external side effect).
3. **The same non-blocking discipline `templates/components/security/auth/`'s `EmailSender` seam already follows applies here**: don't `await` a slow network call synchronously inside the request path just because `BackgroundTasks` exists — the transactional-email recipe's fire-and-forget, non-raising contract is the same shape a `BackgroundTasks` callable should hold (catch and log its own errors; never propagate into a place nothing awaits it).

## What the kit does not provide (be honest about the FastAPI gap)
The kit's FastAPI track has **no vendored real task-queue component** — no arq/Dramatiq/Celery-on-asyncio wiring, no worker Dockerfile, no compatibility-matrix row for any of the three. `references/backend/fastapi.md`'s own "Background work" section names all three as options ("the project's task queue (Celery/arq/taskiq)") without picking one, and no `templates/backend/fastapi/` file wires any of them today (confirmed by inspection at this recipe's `last-verified` date — grep the block before trusting this claim to have not gone stale).

A FastAPI project that needs heavier-than-`BackgroundTasks` work (retryable, scheduled, must-survive-a-restart) has two honest paths, **neither of which this kit ships today**:
- **Add arq** (Redis-backed, `asyncio`-native, the closest fit to a FastAPI project already on Redis for caching/rate-limiting) — a new dependency, a new worker process/entrypoint, and a new compatibility-matrix row the project (or a future `template-author` pass on this kit) would need to add and pin.
- **Run Django's Celery track's Redis instance and worker pattern against the FastAPI app's own task definitions** — viable if the project is a Django+FastAPI hybrid, but not a drop-in for a FastAPI-only project.

Don't cite either as "the kit's arq component" or "the kit's Dramatiq wiring" — neither exists yet. This recipe's own honest gap, same posture as batch 1's `file-upload-s3` recipe noting the kit's missing `s3-uploads` Terraform module.

## Idempotent tasks, retries, and not blocking the request
- **Idempotency**: Celery's default is early-ack (a crash mid-task loses the message); `acks_late=True` + `reject_on_worker_lost=True` (per `celery.md`'s "Idempotency & acks_late") means a task can run **twice** under a worker crash — only turn this on for a task that is safe to run twice (upsert by a stable key, not "increment a counter"). The same principle governs a `BackgroundTasks` callable that might legitimately fire on a retried request — write it so running twice produces the same end state, not a duplicated side effect.
- **Retries**: prefer Celery's declarative `autoretry_for`/`retry_backoff`/`retry_backoff_max`/`retry_jitter` (per `celery.md`'s "Retries") over hand-rolled `try`/`except` — exponential backoff with jitter avoids a thundering-herd retry storm against a struggling downstream dependency.
- **Not blocking the request**: this is the entire point of both halves of this recipe — a Celery task is dispatched with `.delay()`/`.apply_async()` and returns immediately; `BackgroundTasks` schedules its callable to run only after the response has already been sent. Never call a task function directly (`sync_order(1)` instead of `sync_order.delay(1)`) — that executes it synchronously in the request path, silently defeating the whole mechanism.

## Doc fragment
The portable fragment this recipe contributes to the project's root README when applied:

```markdown
### Background jobs
- **Setup (Django track):** Async work runs as Celery tasks (`@shared_task`) against a Redis broker, dispatched with `.delay()`/`.apply_async()` — never called directly. Slow/IO-bound tasks route to a dedicated queue with its own worker. Scheduled work uses `django-celery-beat`'s DB-backed scheduler (`beat` runs as exactly one process, never more). See `references/backend/celery.md`.
- **Setup (FastAPI track):** Light, fire-and-forget work tied to a request uses `BackgroundTasks` — in-process, best-effort, no retry/persistence. The kit ships no real task-queue component for FastAPI today; a project needing retryable/scheduled/durable work adds arq (or another asyncio-native queue) itself — this is a project addition, not a kit-provided wire-up.
- **Secrets:** none new — `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` point at the project's existing Redis instance, resolved the same way as other runtime config.
- **Maintenance:** Keep Celery/`django-celery-beat` on the versions `references/backend/celery.md`'s own "Version check" section names (re-verify before bumping — no compatibility-matrix row exists for either yet). Run exactly one `beat` process. Tasks must stay JSON-serializable (`task_serializer`/`accept_content` = `json`) — never enable `pickle`.
```

---
<!--
Recipe authored via the `recipe-author` skill (Stage 11, #34, batch 2). Wires
the kit's real Celery/Redis convention docs (references/backend/celery.md,
redis.md) on the Django track and FastAPI's native BackgroundTasks per
references/backend/fastapi.md's own "Background work" section on the FastAPI
track. The kit has no vendored FastAPI-native task-queue component (no arq/
Dramatiq wiring) — flagged explicitly rather than cited as existing, matching
batch 1's file-upload-s3 recipe's honesty about the missing s3-uploads module.
-->
