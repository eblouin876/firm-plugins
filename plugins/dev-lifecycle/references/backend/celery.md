<!--
library: celery
versions-covered: "5.x"   # current stable Celery 5.6.3; django-celery-beat 2.9.0
last-verified: 2026-07-12
provenance: auto-generated (pending review)
sources:
  - https://pypi.org/project/celery/
  - https://pypi.org/project/django-celery-beat/
  - https://docs.celeryq.dev/en/stable/userguide/tasks.html
  - https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html
  - https://github.com/celery/celery/releases
-->

# Celery conventions

Idioms for Celery (distributed task queue) with a Redis broker and django-celery-beat for schedules. Read after detecting `celery` / `celery[redis]` in the manifest. Subordinate to the project's existing conventions — if the project's app layout, queue names, or config style differ, the project wins.

## Contents
- Version check
- App setup & autodiscovery
- Broker vs result backend
- Defining tasks
- Calling tasks
- Idempotency & acks_late
- Retries
- Result backend caveats
- Routing & queues
- Periodic tasks (django-celery-beat)
- Workers & concurrency
- Serialization & security
- Pitfalls & testing

## Version check (do this first)
- Current stable is **Celery 5.6.x** (5.6.3); runs on **Python 3.9–3.13** (initial 3.14 support; 3.8 dropped in 5.6). **django-celery-beat 2.9.0** supports **Django 3.2–6.0**. 5.x is not LTS — support runs until 6.x.
- Config keys are **lowercase** (`broker_url`, `result_backend`, `task_always_eager`) since 4.0. Django's `app.config_from_object('django.conf:settings', namespace='CELERY')` maps `CELERY_BROKER_URL` → `broker_url`. Old uppercase (`BROKER_URL`, `CELERY_RESULT_BACKEND`) is legacy — don't emit it.
- Calling style is `.delay()` / `.apply_async()`, not the removed `task.__call__` magic. `retry_backoff`/`autoretry_for` are decorator args (4.0+), not hand-rolled.

## App setup & autodiscovery
Standard Django layout — `proj/celery.py`:
```python
app = Celery('proj')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()   # picks up tasks.py in each INSTALLED_APPS
```
Import the app in `proj/__init__.py` (`from .celery import app as celery_app`) so `@shared_task` binds at startup. Anti-pattern: hardcoding broker URL in `celery.py` — put it in settings as `CELERY_BROKER_URL`.

## Broker vs result backend
Two distinct roles. Redis serves both here: `broker_url = 'redis://redis:6379/0'`, `result_backend = 'redis://redis:6379/1'` (separate DB numbers). The broker is required; the result backend is optional and only needed if you actually consume return values. Redis as broker is fine; for at-least-once durability guarantees prefer RabbitMQ — but Redis is the project default.

## Defining tasks
In Django apps use **`@shared_task`**, not `@app.task` — it doesn't bind to a specific app instance, so reusable apps and `tasks.py` modules work without importing the Celery app (avoids circular imports).
```python
@shared_task(bind=True, max_retries=5)
def sync_order(self, order_id): ...
```
`bind=True` gives `self` (the task instance) for `self.retry`, `self.request.id`, logging.

## Calling tasks
- `task.delay(order_id)` — shorthand for the common case.
- `task.apply_async(args=[order_id], countdown=10, eta=..., queue='io', expires=..., retry=True)` — use when you need eta/countdown, a specific queue, priority, or per-call retry policy.
- Anti-pattern: calling the task function directly (`sync_order(1)`) runs it in-process, not on a worker.

## Idempotency & acks_late
Default is early-ack (message acked before execution) — a crash mid-task loses it. For work that must not be dropped, make the task **idempotent** and set `acks_late=True`; pair it with `reject_on_worker_lost=True` so a hard worker crash re-queues instead of acking:
```python
@shared_task(acks_late=True, reject_on_worker_lost=True)
def charge(payment_id): ...
```
acks_late means a task can run twice — only safe when idempotent.

## Retries
Prefer declarative retries over manual try/except:
```python
@shared_task(autoretry_for=(RequestException,), retry_backoff=5,
             retry_backoff_max=600, retry_jitter=True, max_retries=5)
def fetch(url): ...
```
`retry_backoff=5` → 5,10,20,40… seconds. For manual control use `bind=True` + `raise self.retry(exc=e, countdown=...)`.

## Result backend caveats
Don't use results as a work queue or for inter-task coordination — poll/chain instead. Always bound growth: set `result_expires` (default 1 day) and don't store large payloads. If you never read a task's return, disable results for it (`ignore_result=True`) to save Redis.

## Routing & queues
Isolate slow/IO work onto its own queue so it can't starve fast tasks:
```python
task_routes = {'app.tasks.sync_order': {'queue': 'io'}}
```
Run a dedicated worker per queue (`celery -A proj worker -Q io`). A worker consuming `celery` (default) won't touch `io` unless told to.

## Periodic tasks (django-celery-beat)
Use the DB-backed scheduler so schedules are editable via Django admin, not hardcoded:
```
celery -A proj beat -l INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler
```
(or set `CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'`). Add `django_celery_beat` to `INSTALLED_APPS` and migrate — schedules live in `PeriodicTask`/`CrontabSchedule`/`IntervalSchedule`. **beat is its own process**, separate from workers, and you must run **exactly one** beat — two beats double-fire every scheduled task.

## Workers & concurrency
Default pool is **prefork** (process-per-core, CPU-bound work). For IO-bound tasks use `-P gevent`/`-P threads` with high `--concurrency` (e.g. `-c 100`). For long-running tasks set `worker_prefetch_multiplier = 1` so a worker doesn't hoard queued messages behind one slow task; the default (4) is tuned for short tasks.

## Serialization & security
`json` is the default and correct `task_serializer`/`accept_content`. **Never accept `pickle`** from an untrusted broker — it executes arbitrary code on deserialize. Because payloads are JSON, task args must be JSON-serializable.

## Pitfalls & testing
- Pass **IDs, not ORM objects** — objects serialize stale and bloat the message; re-fetch inside the task. Keep payloads small.
- Test with `task_always_eager = True` (+ `task_eager_propagates = True`) so `.delay()` runs inline and raises — but this bypasses the broker/serialization, so also have integration coverage. Prefer calling the task's underlying function or `.apply()` directly in unit tests and asserting side effects.
