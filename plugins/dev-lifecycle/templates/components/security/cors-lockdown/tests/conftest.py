"""Loads this component's `_core.py`, `fastapi.py`, and `django.py` under
private module names without ever putting this directory on `sys.path` --
see security-headers/tests/conftest.py's docstring for the full rationale
(this component's adapter files are also named `fastapi.py`/`django.py` and
would shadow the real installed packages the same way)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

COMPONENT_DIR = Path(__file__).resolve().parent.parent


def _load(module_name: str, filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, COMPONENT_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


core = _load("_core", "_core.py")
fastapi_mw = _load("cors_lockdown_fastapi_mw", "fastapi.py")
django_mw = _load("cors_lockdown_django_mw", "django.py")


@pytest.fixture(scope="session")
def core_mod() -> ModuleType:
    return core


@pytest.fixture(scope="session")
def fastapi_mod() -> ModuleType:
    return fastapi_mw


@pytest.fixture(scope="session")
def django_mod() -> ModuleType:
    return django_mw
