"""Pins the 500-envelope contract app/main.py's catch-all `Exception`
handler promises (see that module's "Judgment calls" note): ANY unhandled
exception — not just the deliberately-raised `AppError` subclasses — must
still render `ErrorEnvelope` at 500, and must never leak the exception's
own message (`str(exc)`) to the client.

Uses `TestClient(..., raise_server_exceptions=False)` so a bare exception
raised inside a route is caught by the app's own exception handler and
turned into a real HTTP response, instead of re-raising into the test
process the way TestClient does by default. The crashing route itself is
added only to this fixture's own throwaway `FastAPI` app instance (built
fresh per test via `create_app()`), never to the real app — nothing here
ships a real route that crashes."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app.core.db import configure_engine
from app.core.db.session import _reset_engine_for_tests
from app.main import create_app

from .conftest import _test_lifespan

# Import side effect: registers every model on Base.metadata, same as
# conftest.py's own `client` fixture — this fixture builds its own app/
# engine rather than reusing that fixture, so it needs the same side effect.
import app.models  # noqa: F401,E402

_CRASH_MESSAGE = "boom - a genuine bug, must never reach the client"


@pytest.fixture()
def crashing_client() -> Iterator[TestClient]:
    configure_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    app = create_app(lifespan_ctx=_test_lifespan)

    # Throwaway route, added only to this fixture's own app instance, purely
    # to exercise the catch-all Exception handler — never a real shipped
    # route (see module docstring).
    @app.get("/__test_only_crash")
    async def _crash() -> None:
        raise RuntimeError(_CRASH_MESSAGE)

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    _reset_engine_for_tests()


def test_unhandled_exception_returns_enveloped_500_without_leaking_message(
    crashing_client: TestClient,
) -> None:
    response = crashing_client.get("/__test_only_crash")

    assert response.status_code == 500
    body = response.json()
    assert set(body.keys()) == {"error"}
    assert body["error"]["code"] == "internal_error"
    assert body["error"]["details"] is None
    assert _CRASH_MESSAGE not in body["error"]["message"]
    assert "RuntimeError" not in body["error"]["message"]
