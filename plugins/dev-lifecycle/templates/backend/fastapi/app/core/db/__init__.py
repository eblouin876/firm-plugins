"""Package seam for the vendored SQLAlchemy-specific catalog components in
this directory (mixins.py, session.py, repository.py, query.py, schema.py —
each vendored verbatim from templates/components/backend/{db-mixins,
db-session,repository,pagination}/, see each file's own header note).

Those source components are authored as flat, directory-local drop-ins —
repository.py imports `from query import paginate_select` and `from schema
import PageParams, PageResult`; query.py imports `from schema import
PageParams, PageResult` — deliberately NOT package-relative imports (`from
.query import ...`), so a project can vendor just this one directory without
any package-path assumptions (see repository/README.md's and pagination/
README.md's composition contracts). That is exactly what this app does:
these five files live together in app/core/db/, unmodified byte-for-byte
below their header notes.

For those flat sibling imports to resolve when this directory is *also* a
real Python package (app.core.db, imported as such from the rest of the
app), this directory must be on sys.path so `import query` / `import
schema` succeed as top-level module lookups, in addition to being
importable as `app.core.db.query` / `app.core.db.schema`. This is the same
trick each component's own tests/conftest.py uses (inserting the component
directory onto sys.path) — applied once, here, for the real app instead of
per-test.

JUDGMENT CALL (Step 2, Stage 3 #26): this __init__.py is new glue code,
not a vendored file — it's the seam that lets byte-identical vendored
copies compose inside a real package tree without editing their import
statements (which would break clean re-vendoring on the next freshness
audit sync). It also re-exports the names a route/model needs so callers
write `from app.core.db import Base, get_db, AsyncRepository, Page,
PageParams, PageResult` instead of reaching into individual vendored
files.
"""

from __future__ import annotations

import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from mixins import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKey  # noqa: E402
from schema import Page, PageParams, PageResult  # noqa: E402
from session import (  # noqa: E402
    configure_engine,
    get_db,
    get_engine,
    get_sessionmaker,
)
from repository import AsyncRepository  # noqa: E402
from query import paginate_select  # noqa: E402

__all__ = [
    "Base",
    "UUIDPrimaryKey",
    "TimestampMixin",
    "SoftDeleteMixin",
    "Page",
    "PageParams",
    "PageResult",
    "configure_engine",
    "get_db",
    "get_engine",
    "get_sessionmaker",
    "AsyncRepository",
    "paginate_select",
]
