from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_200_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_returns_200_ready(client: TestClient) -> None:
    """Exercises a real `SELECT 1` through get_db against the in-memory
    sqlite engine — proves /readyz is DB-backed, unlike /health."""
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
