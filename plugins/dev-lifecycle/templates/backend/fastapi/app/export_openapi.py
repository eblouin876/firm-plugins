"""Exports this block's OpenAPI schema without needing a live database.

Runnable as `python -m app.export_openapi [output_path]` — writes the
schema as pretty-printed JSON to stdout, or to `output_path` if one is
given. This is the mechanism `packages/api-client`'s `client-generate`
recipe uses (see that package's README's "Stage 3: swapping in the live
schema" section) to keep the committed `openapi.json` fixture in exact
sync with what this block actually emits, instead of a hand-maintained
sample that can silently drift from the real contract.

**Does NOT require a live DATABASE_URL / running Postgres.** `app.openapi()`
builds the schema purely from the FastAPI route/Pydantic-schema
declarations already registered on the app at construction time — it never
touches the database. The database is only ever opened inside `lifespan`
(`app/main.py`), and this script never enters that: it constructs the app
directly via `create_app()` and calls `.openapi()` on it, without starting
an ASGI server or running any lifespan context.

`os.environ.setdefault("DATABASE_URL", ...)` below exists ONLY to satisfy
`AppSettings.database_url`'s required-field check at `Settings()`
construction time (same reasoning, and the same dummy sqlite URL, as
`tests/conftest.py`'s identical line) — this value is never used to open a
real connection. A caller with a real `DATABASE_URL` already set in its
environment is unaffected (`setdefault` only fills in an unset var); the
exported schema is identical either way, since the URL never gets used.
"""

from __future__ import annotations

import json
import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite://")

from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def export_openapi_schema(*, settings: Settings | None = None) -> dict:
    """Builds a fresh app instance — via the `settings=` injection seam
    `create_app()` already exposes for tests (see app/main.py's docstring),
    never the module-level `app.main.app` singleton — and returns
    `app.openapi()`: the exact dict FastAPI would serve at `/openapi.json`
    for a real boot with these settings. Defaults to a `Settings()` built
    from whatever `DATABASE_URL` is in the environment at call time (the
    dummy value `setdefault` above supplies if nothing real is set)."""
    resolved = settings if settings is not None else Settings(database_url=os.environ["DATABASE_URL"])
    app = create_app(settings=resolved)
    return app.openapi()


def main(argv: list[str]) -> int:
    schema = export_openapi_schema()
    output = json.dumps(schema, indent=2) + "\n"
    if argv:
        with open(argv[0], "w", encoding="utf-8") as fh:
            fh.write(output)
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
