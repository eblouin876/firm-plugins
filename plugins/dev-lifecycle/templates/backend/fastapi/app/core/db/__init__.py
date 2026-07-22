"""Package seam for the vendored SQLAlchemy-specific catalog components in
this directory (mixins.py, session.py, repository.py, query.py, schema.py —
each vendored from templates/components/backend/{db-mixins,
db-session,repository,pagination}/, see each file's own header note).

Those source components are authored as flat, directory-local drop-ins in
the component catalog itself — repository.py imports `from query import
paginate_select` and `from schema import PageParams, PageResult`; query.py
imports `from schema import PageParams, PageResult` — deliberately not
package-relative there, so a project can vendor just this one directory
with no package-path assumptions (see repository/README.md's and
pagination/README.md's composition contracts).

This app instead composes them as a REAL intra-package, with the two
files that have cross-imports (query.py, repository.py) rewritten to
RELATIVE imports (`from .schema import ...`, `from .query import ...`)
rather than a sys.path shim onto this directory. That is the invariant
README.md's "Vendored components" section documents: each vendored
component lands here as a self-contained subpackage using relative
imports, with NO global sys.path manipulation. A `sys.path.insert` here
would expose this directory's modules (`mixins`, `session`, `repository`,
`query`, `schema`) as TOP-LEVEL, process-wide module names — generic names
like `schema` and `query` that a future vendored component (Step 3b's
security components, or any other block importing this app in-process)
could collide with silently. Relative imports avoid that seam entirely.

Consequence: query.py's and repository.py's cross-import lines are no
longer byte-identical to their component-catalog source below the header
note — each carries its own header drift note explaining the adaptation
("imports adapted to relative for in-app packaging"). mixins.py,
session.py, and schema.py have no cross-imports to adapt and remain
byte-identical.

This __init__.py is itself new glue code, not a vendored file — it's the
seam that lets the (now relatively-importing) vendored copies compose
inside a real package tree. It also re-exports the names a route/model
needs so callers write `from app.core.db import Base, get_db,
AsyncRepository, Page, PageParams, PageResult` instead of reaching into
individual vendored files.
"""

from __future__ import annotations

from .mixins import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKey
from .schema import Page, PageParams, PageResult
from .session import (
    configure_engine,
    get_db,
    get_engine,
    get_sessionmaker,
)
from .repository import AsyncRepository
from .query import paginate_select

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
