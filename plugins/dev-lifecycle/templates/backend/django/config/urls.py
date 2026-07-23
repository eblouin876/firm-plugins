"""Root URLconf. Not vendored — standard Django project boilerplate. Empty
route list as of this step (Stage 4 Step 1, #27): no DRF views/routers exist
yet — Step 2 wires the Item ViewSet + router here, reproducing the FastAPI
block's `/items` routes (see backend/fastapi/README.md's "Composition
contract" EXPOSES table for the exact route set this app converges on)."""

from __future__ import annotations

from django.urls import path

urlpatterns: list = [
    # TODO(Stage 4 Step 2, #27): wire a DRF router here exposing
    # GET/POST /items, GET/PATCH/DELETE /items/{id} — see
    # backend/fastapi/app/api/routers/items.py for the route/status-code
    # contract this block's DRF views must reproduce wire-for-wire.
]

__all__ = ["urlpatterns"]
