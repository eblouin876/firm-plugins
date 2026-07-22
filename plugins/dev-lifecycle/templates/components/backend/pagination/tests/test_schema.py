"""Tests for the neutral pagination shapes (schema.py). Pydantic only — no
SQLAlchemy import anywhere in this file, matching schema.py itself."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from schema import Page, PageParams, PageResult


# --- PageParams --------------------------------------------------------


def test_page_params_defaults():
    params = PageParams()
    assert params.page == 1
    assert params.size == 20


def test_page_params_offset_math():
    assert PageParams(page=1, size=20).offset == 0
    assert PageParams(page=2, size=20).offset == 20
    assert PageParams(page=3, size=10).offset == 20


@pytest.mark.parametrize("page", [0, -1])
def test_page_params_rejects_non_positive_page(page):
    with pytest.raises(ValidationError):
        PageParams(page=page)


@pytest.mark.parametrize("size", [0, -1, 201])
def test_page_params_rejects_out_of_bounds_size(size):
    with pytest.raises(ValidationError):
        PageParams(size=size)


def test_page_params_accepts_max_size():
    assert PageParams(size=200).size == 200


def test_page_params_rejects_unknown_field():
    with pytest.raises(ValidationError):
        PageParams(page=1, offset=0)  # 'offset' is a property, not a field


# --- Page.create: pagination math ---------------------------------------


def test_page_create_computes_pages_evenly_divisible():
    page = Page.create([1, 2, 3], total=9, params=PageParams(page=1, size=3))
    assert page.pages == 3


def test_page_create_computes_pages_with_remainder():
    page = Page.create([1, 2], total=10, params=PageParams(page=5, size=3))
    assert page.pages == 4  # ceil(10 / 3) == 4


def test_page_create_empty_result_set_has_zero_pages():
    page = Page.create([], total=0, params=PageParams(page=1, size=20))
    assert page.pages == 0
    assert page.items == []
    assert page.total == 0


def test_page_create_single_item_single_page():
    page = Page.create(["only"], total=1, params=PageParams(page=1, size=20))
    assert page.pages == 1
    assert page.total == 1


def test_page_create_preserves_page_and_size_from_params():
    params = PageParams(page=4, size=7)
    page = Page.create(["a"], total=50, params=params)
    assert page.page == 4
    assert page.size == 7


# --- Page[T]: generic works with a plain type and a Pydantic model ------


def test_page_generic_with_plain_type():
    page: Page[int] = Page.create([1, 2, 3], total=3, params=PageParams())
    assert page.items == [1, 2, 3]
    dumped = page.model_dump()
    assert dumped["items"] == [1, 2, 3]
    assert dumped["total"] == 3


class _WidgetOut(BaseModel):
    name: str


def test_page_generic_with_pydantic_model():
    widgets = [_WidgetOut(name="a"), _WidgetOut(name="b")]
    page: Page[_WidgetOut] = Page.create(widgets, total=2, params=PageParams())
    dumped = page.model_dump()
    assert dumped["items"] == [{"name": "a"}, {"name": "b"}]


def test_page_is_a_strict_wire_model_no_arbitrary_types_allowed():
    # MEDIUM-2 fix: Page must stay strict -- arbitrary_types_allowed was
    # removed so a route can never accidentally return raw ORM rows
    # through it.
    assert Page.model_config.get("arbitrary_types_allowed") is not True


def test_page_serialization_shape_has_exactly_the_expected_keys():
    page = Page.create([1], total=1, params=PageParams(page=1, size=20))
    assert set(page.model_dump().keys()) == {"items", "total", "page", "size", "pages"}


# --- PageResult: the internal, non-wire container ---------------------------


def test_page_result_holds_items_total_page_size():
    result = PageResult(items=["a", "b"], total=10, page=2, size=2)
    assert result.items == ["a", "b"]
    assert result.total == 10
    assert result.page == 2
    assert result.size == 2


def test_page_result_is_not_a_pydantic_model():
    result = PageResult(items=[], total=0, page=1, size=20)
    assert not hasattr(result, "model_dump")


def test_page_result_holds_an_arbitrary_non_pydantic_object():
    # This is exactly the case Page[T] used to accommodate via
    # arbitrary_types_allowed -- now it's PageResult's job, not Page's.
    class _NotAPydanticModel:
        def __init__(self, value: str) -> None:
            self.value = value

    obj = _NotAPydanticModel("plain-object")
    result = PageResult(items=[obj], total=1, page=1, size=20)
    assert result.items[0].value == "plain-object"


def test_a_route_maps_a_page_result_into_a_wire_page_via_page_create():
    # The documented route-layer pattern: PageResult -> mapped items ->
    # Page.create(...).
    result = PageResult(items=[1, 2, 3], total=3, page=1, size=20)
    page = Page.create(result.items, total=result.total, params=PageParams(page=result.page, size=result.size))
    assert page.items == [1, 2, 3]
    assert page.pages == 1
