"""Loads this component's `_core.py`, `fastapi.py`, and `django.py` as
importable test modules WITHOUT ever inserting this component's directory
onto `sys.path`.

Why not the simpler `sys.path.insert(0, ...)` pattern the single-file Step 2
components use (see `secrets-loading/tests/conftest.py`): this component's
adapter files are deliberately named `fastapi.py` and `django.py` (matching
the framework they wire up — see each file's own docstring). Putting this
directory on `sys.path` would shadow the REAL installed `fastapi`/`django`
packages for the rest of the test session — `import fastapi` from a test
file would resolve to this component's own middleware module instead of the
framework. Instead, each file is loaded individually via `importlib` under
a private module name, and `_core` (which has no name collision with
anything installed) is additionally registered in `sys.modules` under its
own bare name `_core` — exactly the name `fastapi.py`/`django.py` import it
under (`import _core`) — so their own bare imports resolve without needing
this directory on `sys.path` at all.

This mirrors the real deployment shape: once copied into
`app/core/security/security_headers/`, `fastapi.py`/`django.py` are reached
by callers as `app.core.security.security_headers.fastapi` /
`...django`, never as a bare top-level `import fastapi`/`import django` —
so there is no shadowing risk in production, only in this flat test
harness, which is exactly what this conftest works around.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import django as django_framework  # the REAL installed Django package
import pytest
from django.conf import settings

COMPONENT_DIR = Path(__file__).resolve().parent.parent


def _load(module_name: str, filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, COMPONENT_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


if not settings.configured:
    settings.configure(
        DEBUG=True,
        ALLOWED_HOSTS=["*"],
        USE_TZ=True,
        SECRET_KEY="test-secret-key-not-real",
        DATABASES={},
        MIDDLEWARE=[],
        DEFAULT_CHARSET="utf-8",
    )
    django_framework.setup()

# _core has no name collision with any installed package, so it's safe (and
# necessary, for fastapi.py/django.py's own bare `import _core` to resolve)
# to register it under its real, unqualified name.
core = _load("_core", "_core.py")
fastapi_mw = _load("security_headers_fastapi_mw", "fastapi.py")
django_mw = _load("security_headers_django_mw", "django.py")


@pytest.fixture(scope="session")
def core_mod() -> ModuleType:
    return core


@pytest.fixture(scope="session")
def fastapi_mod() -> ModuleType:
    return fastapi_mw


@pytest.fixture(scope="session")
def django_mod() -> ModuleType:
    return django_mw
