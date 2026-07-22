from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def _create_item(client: TestClient, *, name: str = "Widget", description: str | None = "A widget.") -> dict:
    response = client.post("/items", json={"name": name, "description": description})
    assert response.status_code == 201, response.text
    return response.json()


def test_create_and_get_item_round_trips(client: TestClient) -> None:
    created = _create_item(client)
    assert created["name"] == "Widget"
    assert created["description"] == "A widget."
    assert uuid.UUID(created["id"])  # a real UUID, not e.g. an int
    assert created["created_at"]
    assert created["updated_at"]

    fetched = client.get(f"/items/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == created


def test_list_items_returns_page_envelope(client: TestClient) -> None:
    for i in range(3):
        _create_item(client, name=f"Item {i}")

    response = client.get("/items")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"items", "total", "page", "size", "pages"}
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["size"] == 20
    assert body["pages"] == 1
    assert len(body["items"]) == 3


def test_list_items_pagination_params(client: TestClient) -> None:
    for i in range(5):
        _create_item(client, name=f"Item {i}")

    response = client.get("/items", params={"page": 2, "size": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 5
    assert body["page"] == 2
    assert body["size"] == 2
    assert body["pages"] == 3
    assert len(body["items"]) == 2


def test_update_item(client: TestClient) -> None:
    created = _create_item(client)
    response = client.patch(f"/items/{created['id']}", json={"name": "Renamed"})
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Renamed"
    assert body["description"] == created["description"]  # unset field untouched


def test_delete_item_then_get_is_404(client: TestClient) -> None:
    created = _create_item(client)
    delete_response = client.delete(f"/items/{created['id']}")
    assert delete_response.status_code == 204

    get_response = client.get(f"/items/{created['id']}")
    assert get_response.status_code == 404
    body = get_response.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["message"]


def test_get_missing_item_returns_enveloped_404(client: TestClient) -> None:
    response = client.get(f"/items/{uuid.uuid4()}")
    assert response.status_code == 404
    body = response.json()
    assert body == {
        "error": {
            "code": "not_found",
            "message": body["error"]["message"],
            "details": None,
        }
    }


def test_create_item_with_invalid_body_returns_enveloped_422(client: TestClient) -> None:
    # `name` is required and min_length=1 — omit it entirely.
    response = client.post("/items", json={"description": "no name"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_failed"
    assert body["error"]["message"]
    assert isinstance(body["error"]["details"], list)
    assert len(body["error"]["details"]) >= 1
    assert body["error"]["details"][0]["field"].endswith("name")
    assert body["error"]["details"][0]["message"]


def test_create_item_rejects_unknown_field(client: TestClient) -> None:
    """extra="forbid" on ItemCreate — an unrecognized field is a 422, not
    silently dropped."""
    response = client.post("/items", json={"name": "Widget", "bogus": "nope"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"
