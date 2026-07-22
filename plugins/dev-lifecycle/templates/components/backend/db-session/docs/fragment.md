<!-- fragment: block:components/backend/db-session -->

## Setup
Copy `session.py` into `app/core/db/session.py`, alongside `mixins.py` and
`repository.py`. Call `configure_engine(settings.database_url)` once at app
startup (a FastAPI lifespan handler or `on_startup` hook); every route then
depends on the session directly with `Depends(get_db)` — no per-route
wiring. `DATABASE_URL` must name an async driver (`postgresql+asyncpg://`
in prod, `sqlite+aiosqlite://` in tests) — a bare `postgresql://`/
`sqlite://`/`mysql://` scheme raises `ValueError` immediately, naming the
correct async driver, instead of failing deep inside `create_async_engine`.

## Secrets
| `DATABASE_URL` | db-session | Not read from the environment by this module directly — pass it to `configure_engine()`, typically sourced from `settings/`'s `DATABASE_URL` field. |

## Maintenance
SQLAlchemy-specific — Django's own connection/transaction model (Stage 4)
has no `AsyncSession`/`async_sessionmaker` equivalent; this file is not
reused there.
