from __future__ import annotations

from fastapi.testclient import TestClient


def test_login_stub_returns_501(client: TestClient) -> None:
    response = client.post("/auth/login", json={"email": "a@example.com", "password": "secret"})
    assert response.status_code == 501
    assert response.json()["detail"]


def test_refresh_stub_returns_501(client: TestClient) -> None:
    response = client.post("/auth/refresh", json={"refresh_token": "whatever"})
    assert response.status_code == 501
    assert response.json()["detail"]


def test_me_stub_returns_501_without_credentials(client: TestClient) -> None:
    response = client.get("/auth/me")
    assert response.status_code == 501
    assert response.json()["detail"]


def test_me_stub_returns_501_with_bearer_credentials(client: TestClient) -> None:
    response = client.get("/auth/me", headers={"Authorization": "Bearer fake-token"})
    assert response.status_code == 501
    assert response.json()["detail"]


def test_bearer_scheme_is_declared_in_openapi(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    security_schemes = schema.get("components", {}).get("securitySchemes", {})
    assert "HTTPBearer" in security_schemes
    assert security_schemes["HTTPBearer"]["type"] == "http"
    assert security_schemes["HTTPBearer"]["scheme"] == "bearer"
