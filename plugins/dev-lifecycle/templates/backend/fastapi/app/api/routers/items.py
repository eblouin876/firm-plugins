"""Full CRUD for `Item` — the contract exemplar router. Every handler is
thin: validate (via the Pydantic schema FastAPI already ran), delegate to
`AsyncRepository`, map ORM -> output schema, return. Per repository/
README.md's "Wire vs internal" contract, `list()`'s `PageResult` is mapped
to `ItemOut` and wrapped in `Page.create(...)` HERE, in the route — never
returned directly."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import AsyncRepository, Page, PageParams, get_db
from app.core.errors import NotFoundError
from app.models.item import Item
from app.schemas.item import ItemCreate, ItemOut, ItemUpdate

router = APIRouter(prefix="/items", tags=["items"])


@router.get("", response_model=Page[ItemOut], summary="List Items")
async def list_items(
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Page[ItemOut]:
    repo = AsyncRepository(db, Item)
    result = await repo.list(params=params)
    mapped = [ItemOut.model_validate(obj) for obj in result.items]
    return Page.create(mapped, total=result.total, params=params)


@router.post(
    "",
    response_model=ItemOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create Item",
)
async def create_item(payload: ItemCreate, db: AsyncSession = Depends(get_db)) -> ItemOut:
    repo = AsyncRepository(db, Item)
    obj = await repo.create(**payload.model_dump())
    return ItemOut.model_validate(obj)


@router.get("/{item_id}", response_model=ItemOut, summary="Get Item")
async def get_item(item_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> ItemOut:
    repo = AsyncRepository(db, Item)
    obj = await repo.get(item_id)
    if obj is None:
        raise NotFoundError(f"Item {item_id} was not found.")
    return ItemOut.model_validate(obj)


@router.patch("/{item_id}", response_model=ItemOut, summary="Update Item")
async def update_item(
    item_id: uuid.UUID,
    payload: ItemUpdate,
    db: AsyncSession = Depends(get_db),
) -> ItemOut:
    repo = AsyncRepository(db, Item)
    obj = await repo.get(item_id)
    if obj is None:
        raise NotFoundError(f"Item {item_id} was not found.")
    updates = payload.model_dump(exclude_unset=True)
    obj = await repo.update(obj, **updates)
    return ItemOut.model_validate(obj)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete Item")
async def delete_item(item_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> None:
    repo = AsyncRepository(db, Item)
    obj = await repo.get(item_id)
    if obj is None:
        raise NotFoundError(f"Item {item_id} was not found.")
    await repo.delete(obj)
