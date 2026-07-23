"""Custom DRF pagination class — Stage 4 Step 2 (#27), fix round — emitting
`core.contract.pagination.Page`'s `{items, total, page, size, pages}` shape
over HTTP. DRF's own `PageNumberPagination` default emits `{count, next,
previous, results}`; wiring THIS class as `DEFAULT_PAGINATION_CLASS`
(config/settings.py) is what makes `GET /items` wire-identical to
backend/fastapi's `Page[ItemOut]` response (app/api/routers/items.py's
`list_items` + app/core/db/schema.py's `Page.create`, the same
`Page.create` classmethod this class calls — `core/contract/pagination.py`
is the byte-copy vendored for exactly this reuse).

`paginate_queryset` is fully overridden (not just tuned via class
attributes) so `page`/`size` are validated through the SAME vendored
`core.contract.pagination.PageParams` FastAPI's own `Depends(PageParams)`
uses, turning what was previously an accepted per-framework divergence
(DRF silently clamping/accepting out-of-bounds values) into real
conformance: `page=0`/`page=-1`/`size=0`/`size>200` now 422 here exactly
like they do on the FastAPI block, and a `page` past the last one returns
200 with `items: []` (matching FastAPI's offset-past-end behavior) instead
of DRF's own default 404 "Invalid page"."""

from __future__ import annotations

from django.core.paginator import EmptyPage, Paginator
from pydantic import ValidationError as PydanticValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from core.contract.errors import ErrorDetail, ValidationFailedError
from core.contract.pagination import Page, PageParams

_VALIDATION_MESSAGE = "Invalid pagination parameters."


class _EmptyPage:
    """Stand-in for `django.core.paginator.Page`, used only when the
    requested `page` is past the last real page. `object_list = []` is
    what `paginate_queryset` returns to the view (rendering as `items: []`
    over HTTP); `.number`/`.paginator` are kept real so
    `get_paginated_response` below computes `total`/`pages` exactly as it
    would for any other page — matching FastAPI's offset-past-end
    behavior (200, not a 404) for the same out-of-range request."""

    object_list: list = []

    def __init__(self, number: int, paginator: Paginator) -> None:
        self.number = number
        self.paginator = paginator


class ContractPageNumberPagination(PageNumberPagination):
    """`page`/`size` query params (1-indexed page, validated against
    `core.contract.pagination.PageParams`'s own bounds: `page: int =
    Field(ge=1)`, `size: int = Field(ge=1, le=200)`) field-for-field.

    ACCEPTED DIVERGENCE (documented per this step's own instructions, not
    forced): `PageParams.model_config = ConfigDict(extra="forbid")` means
    an unrecognized query param on the FastAPI block is a hard 422 (e.g. an
    old, unmigrated caller still sending `?offset=5&limit=20`). This class
    still constructs `PageParams` only from the two recognized query
    params (`page`/`size`) it reads by name — an unrelated unknown query
    param is silently ignored here, the same as every other DRF endpoint's
    normal query-param handling. Enforcing a closed query-param surface
    project-wide (a drf-spectacular schema validation step, a
    request-level middleware) is a bigger, separate decision than this one
    pagination class should make unilaterally — see this block's README,
    "Conformance"."""

    page_query_param = "page"
    page_size_query_param = "size"
    page_size = 20
    max_page_size = 200

    def paginate_queryset(self, queryset, request, view=None):
        page_raw = request.query_params.get(self.page_query_param, 1)
        size_raw = request.query_params.get(self.page_size_query_param, self.page_size)

        try:
            params = PageParams(page=page_raw, size=size_raw)
        except PydanticValidationError as exc:
            details = [
                ErrorDetail(field=".".join(str(part) for part in err["loc"]) or None, message=err["msg"])
                for err in exc.errors()
            ]
            # AppError, not a bare ValueError -- core.exceptions.exception_handler's
            # `isinstance(exc, AppError)` branch renders this as the SAME
            # `{"error": {"code": "validation_failed", ...}}` envelope at
            # 422 every other validation failure in this block uses.
            raise ValidationFailedError(_VALIDATION_MESSAGE, details=details) from None

        paginator = Paginator(queryset, params.size)
        try:
            self.page = paginator.page(params.page)
        except EmptyPage:
            # `params.page` is already validated >= 1 (PageParams above) --
            # an EmptyPage here only ever means "past the last real page",
            # never "not an integer"/"less than 1". Tolerate it as an empty
            # page rather than DRF's own default 404 "Invalid page".
            self.page = _EmptyPage(params.page, paginator)

        self.request = request
        return list(self.page.object_list)

    def get_paginated_response(self, data):
        params = PageParams(page=self.page.number, size=self.page.paginator.per_page)
        page = Page.create(list(data), total=self.page.paginator.count, params=params)
        return Response(page.model_dump(mode="json"))
