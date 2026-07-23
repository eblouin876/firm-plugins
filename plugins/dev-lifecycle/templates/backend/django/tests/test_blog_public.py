"""Stage 13d public read (issue #54, the deferred acceptance item) — the
PUBLIC, unauthenticated blog read surface (`core/views.py`'s
`PublicBlogPostListView`/`PublicBlogPostDetailView`). The DRF counterpart
to `backend/fastapi`'s `tests/test_blog_public.py` — same test names/
scenarios/payloads (see that module's own docstring), ported to this
block's `APIClient`/`_admin_headers`/`_create_post` helpers (`.test_blog`).

**The end-to-end stored-XSS proof
(`test_public_detail_serves_sanitized_html_not_the_raw_xss_payload`) is
this module's own load-bearing test** — same posture the FastAPI track's
identically-named test documents for itself.

`@pytest.mark.django_db(transaction=True)` module-wide — same rationale
`tests/test_blog.py`'s own module docstring documents in full."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from .test_blog import _admin_headers, _create_post

pytestmark = pytest.mark.django_db(transaction=True)


def _publish(client: APIClient, headers: dict, post_id: str) -> dict:
    response = client.post(f"/admin/blog/posts/{post_id}/publish", **headers)
    assert response.status_code == 200, response.content
    return response.json()


# ---------------------------------------------------------------------------
# No auth required
# ---------------------------------------------------------------------------


def test_list_requires_no_auth() -> None:
    client = APIClient()
    response = client.get("/blog/posts")
    assert response.status_code == 200, response.content


def test_detail_requires_no_auth_for_an_unknown_slug() -> None:
    client = APIClient()
    response = client.get("/blog/posts/nope")
    assert response.status_code == 404, response.content


# ---------------------------------------------------------------------------
# Published posts are served
# ---------------------------------------------------------------------------


def test_published_post_is_served_by_list_and_detail() -> None:
    client = APIClient()
    headers = _admin_headers(client)
    created = _create_post(client, headers, title="Published Post")
    _publish(client, headers, created["id"])

    list_response = client.get("/blog/posts")
    assert list_response.status_code == 200, list_response.content
    slugs = {item["slug"] for item in list_response.json()["items"]}
    assert created["slug"] in slugs

    detail_response = client.get(f"/blog/posts/{created['slug']}")
    assert detail_response.status_code == 200, detail_response.content
    body = detail_response.json()
    assert body["slug"] == created["slug"]
    assert body["title"] == "Published Post"
    assert body["body_html"] == "<p>Hello <strong>world</strong></p>"


def test_public_summary_shape_has_no_body_and_no_status() -> None:
    client = APIClient()
    headers = _admin_headers(client)
    created = _create_post(client, headers, title="Shape Check")
    _publish(client, headers, created["id"])

    response = client.get("/blog/posts")
    assert response.status_code == 200, response.content
    item = next(item for item in response.json()["items"] if item["slug"] == created["slug"])
    assert "body_json" not in item
    assert "body_html" not in item
    assert "status" not in item
    assert set(item.keys()) == {"id", "title", "slug", "excerpt", "published_at", "author_id", "created_at"}


def test_public_detail_never_has_body_json() -> None:
    client = APIClient()
    headers = _admin_headers(client)
    created = _create_post(client, headers)
    _publish(client, headers, created["id"])

    response = client.get(f"/blog/posts/{created['slug']}")
    assert response.status_code == 200, response.content
    assert "body_json" not in response.json()


def test_excerpt_is_derived_plain_text_from_body_html() -> None:
    client = APIClient()
    headers = _admin_headers(client)
    created = _create_post(
        client,
        headers,
        title="Excerpt Check",
        body_html="<p>Hello <strong>world</strong>, this is the body.</p>",
    )
    _publish(client, headers, created["id"])

    response = client.get("/blog/posts")
    item = next(item for item in response.json()["items"] if item["slug"] == created["slug"])
    assert item["excerpt"] == "Hello world, this is the body."
    assert "<" not in item["excerpt"]


def test_excerpt_is_none_for_a_body_that_strips_to_nothing() -> None:
    client = APIClient()
    headers = _admin_headers(client)
    created = _create_post(client, headers, title="Empty Excerpt", body_html="<hr>")
    _publish(client, headers, created["id"])

    response = client.get("/blog/posts")
    item = next(item for item in response.json()["items"] if item["slug"] == created["slug"])
    assert item["excerpt"] is None


# ---------------------------------------------------------------------------
# Draft and soft-deleted posts are never served
# ---------------------------------------------------------------------------


def test_draft_post_is_excluded_from_the_public_list() -> None:
    client = APIClient()
    headers = _admin_headers(client)
    draft = _create_post(client, headers, title="Still A Draft")

    response = client.get("/blog/posts")
    assert response.status_code == 200, response.content
    slugs = {item["slug"] for item in response.json()["items"]}
    assert draft["slug"] not in slugs


def test_draft_posts_slug_404s_identically_to_an_unknown_slug() -> None:
    client = APIClient()
    headers = _admin_headers(client)
    draft = _create_post(client, headers, title="Secret Post", slug="secret-post")

    draft_response = client.get(f"/blog/posts/{draft['slug']}")
    unknown_response = client.get("/blog/posts/this-slug-does-not-exist")

    assert draft_response.status_code == 404, draft_response.content
    assert unknown_response.status_code == 404, unknown_response.content
    draft_body, unknown_body = draft_response.json(), unknown_response.json()
    assert draft_body.keys() == unknown_body.keys() == {"error"}
    assert draft_body["error"].keys() == unknown_body["error"].keys()
    assert draft_body["error"]["code"] == unknown_body["error"]["code"] == "not_found"
    assert draft_body["error"]["message"] == f"Blog post '{draft['slug']}' was not found."
    assert unknown_body["error"]["message"] == "Blog post 'this-slug-does-not-exist' was not found."
    for message in (draft_body["error"]["message"], unknown_body["error"]["message"]):
        assert "draft" not in message.lower()
        assert "unpublish" not in message.lower()


def test_soft_deleted_post_is_excluded_from_list_and_detail_404s() -> None:
    client = APIClient()
    headers = _admin_headers(client)
    created = _create_post(client, headers, title="Will Be Deleted")
    _publish(client, headers, created["id"])

    delete_response = client.delete(f"/admin/blog/posts/{created['id']}", **headers)
    assert delete_response.status_code == 204, delete_response.content

    list_response = client.get("/blog/posts")
    slugs = {item["slug"] for item in list_response.json()["items"]}
    assert created["slug"] not in slugs

    detail_response = client.get(f"/blog/posts/{created['slug']}")
    assert detail_response.status_code == 404, detail_response.content


def test_unpublished_post_reverts_to_hidden_from_the_public_surface() -> None:
    client = APIClient()
    headers = _admin_headers(client)
    created = _create_post(client, headers, title="Published Then Unpublished")
    _publish(client, headers, created["id"])
    assert client.get(f"/blog/posts/{created['slug']}").status_code == 200

    unpublish_response = client.post(f"/admin/blog/posts/{created['id']}/unpublish", **headers)
    assert unpublish_response.status_code == 200, unpublish_response.content

    response = client.get(f"/blog/posts/{created['slug']}")
    assert response.status_code == 404, response.content


# ---------------------------------------------------------------------------
# THE end-to-end stored-XSS proof (public read of the already-sanitized value)
# ---------------------------------------------------------------------------


def test_public_detail_serves_sanitized_html_not_the_raw_xss_payload() -> None:
    client = APIClient()
    headers = _admin_headers(client)
    raw_html = (
        "<p>Intro paragraph with <strong>bold</strong> text.</p>"
        '<a href="javascript:alert(1)">click me</a>'
        "<img src=x onerror=alert(1)>"
        "<script>alert(1)</script>"
        '<p onclick="alert(1)">click handler</p>'
        '<a href="https://example.com" title="Example">safe link</a>'
    )
    created = _create_post(client, headers, title="Public XSS Test", body_html=raw_html)
    _publish(client, headers, created["id"])

    response = client.get(f"/blog/posts/{created['slug']}")
    assert response.status_code == 200, response.content
    served_html = response.json()["body_html"]

    assert "javascript:" not in served_html
    assert "onerror" not in served_html
    assert "onclick" not in served_html
    assert "<script" not in served_html
    assert "</script>" not in served_html
    assert "alert(1)" not in served_html
    assert "<img" not in served_html
    assert "<p>Intro paragraph with <strong>bold</strong> text.</p>" in served_html
    assert '<a href="https://example.com" title="Example" rel="noopener noreferrer nofollow">safe link</a>' in (
        served_html
    )

    list_response = client.get("/blog/posts")
    item = next(item for item in list_response.json()["items"] if item["slug"] == created["slug"])
    assert "<" not in item["excerpt"]
    assert "alert(1)" not in item["excerpt"]


# ---------------------------------------------------------------------------
# Pagination + newest-first ordering
# ---------------------------------------------------------------------------


def test_list_paginates_and_orders_newest_first_by_published_at() -> None:
    client = APIClient()
    headers = _admin_headers(client)
    first = _create_post(client, headers, title="First Published")
    _publish(client, headers, first["id"])
    second = _create_post(client, headers, title="Second Published")
    _publish(client, headers, second["id"])
    third = _create_post(client, headers, title="Third Published")
    _publish(client, headers, third["id"])

    response = client.get("/blog/posts", {"page": 1, "size": 2})
    assert response.status_code == 200, response.content
    body = response.json()
    assert {"items", "total", "page", "size", "pages"} <= body.keys()
    assert body["size"] == 2
    assert body["total"] >= 3
    slugs_page_1 = [item["slug"] for item in body["items"]]
    assert slugs_page_1[0] == third["slug"]
    assert slugs_page_1[1] == second["slug"]

    page_2 = client.get("/blog/posts", {"page": 2, "size": 2})
    assert page_2.status_code == 200, page_2.content
    slugs_page_2 = [item["slug"] for item in page_2.json()["items"]]
    assert first["slug"] in slugs_page_2


def test_list_size_is_bounded_by_the_pagination_components_cap() -> None:
    client = APIClient()
    response = client.get("/blog/posts", {"size": 500})
    assert response.status_code == 422, response.content
    assert response.json()["error"]["code"] == "validation_failed"
