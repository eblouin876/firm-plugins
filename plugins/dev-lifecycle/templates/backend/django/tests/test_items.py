"""Basic CRUD smoke tests for `ItemViewSet` — Stage 4 Step 2 (#27), commit 1
verification ("a basic item create/list/get works via DRF test client").
Full conformance-proof (error envelopes, pagination shape byte-equality) is
`tests/test_conformance_errors.py` / `tests/test_conformance_pagination.py`,
added in this step's second commit."""

from __future__ import annotations

import uuid

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_create_item(api_client: APIClient) -> None:
    response = api_client.post("/items", {"name": "Widget", "description": "A thing"}, format="json")

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Widget"
    assert body["description"] == "A thing"
    uuid.UUID(body["id"])  # well-formed UUID string
    assert "created_at" in body
    assert "updated_at" in body
    assert "deleted_at" not in body


def test_create_item_omitted_description_is_null(api_client: APIClient) -> None:
    response = api_client.post("/items", {"name": "Widget"}, format="json")

    assert response.status_code == 201
    assert response.json()["description"] is None


def test_list_items(api_client: APIClient) -> None:
    api_client.post("/items", {"name": "One"}, format="json")
    api_client.post("/items", {"name": "Two"}, format="json")

    response = api_client.get("/items")

    assert response.status_code == 200


def test_get_item(api_client: APIClient) -> None:
    created = api_client.post("/items", {"name": "Gadget"}, format="json").json()

    response = api_client.get(f"/items/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_update_item(api_client: APIClient) -> None:
    created = api_client.post("/items", {"name": "Original"}, format="json").json()

    response = api_client.patch(f"/items/{created['id']}", {"name": "Renamed"}, format="json")

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"


def test_delete_item_is_soft_delete(api_client: APIClient) -> None:
    """Checks the soft-delete state directly via the ORM rather than
    following up with a GET on the now-missing id: `get_object()`
    (core/views.py) raises `core.contract.errors.NotFoundError` — an
    `AppError`, not a DRF `Http404`/`NotFound` — which DRF's own default
    exception handler doesn't recognize and this commit hasn't wired
    `core.exceptions.exception_handler` yet (that lands in this step's
    second commit). The 404-over-HTTP behavior is proven in
    `tests/test_conformance_errors.py`, added alongside that handler."""
    from core.models import Item

    created = api_client.post("/items", {"name": "Doomed"}, format="json").json()

    response = api_client.delete(f"/items/{created['id']}")

    assert response.status_code == 204
    # Invisible to the default (soft-delete-scoped) manager...
    assert not Item.objects.filter(pk=created["id"]).exists()
    # ...but still present via the unscoped escape hatch, with deleted_at set.
    obj = Item.all_objects.get(pk=created["id"])
    assert obj.deleted_at is not None
