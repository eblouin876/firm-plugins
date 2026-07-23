"""Stage 13d (deferred acceptance item, issue #54) — the PUBLIC,
unauthenticated blog read surface (`app/api/routers/blog_public.py`):
`GET /blog/posts` and `GET /blog/posts/{slug}`. Reuses `tests/test_blog.py`'s
own admin-side fixtures/helpers (`auth_client`, `email_sender`,
`_admin_headers`, `_create_post`, `_reset_admin_rate_limit`) to get a post
into whatever state a given test needs (draft, published, soft-deleted) —
this module never calls any `/admin/blog/*` endpoint's behavior directly,
only reuses the test-side plumbing that already knows how to drive it.

**The end-to-end stored-XSS proof
(`test_public_detail_serves_sanitized_html_not_the_raw_xss_payload`) is
this module's own load-bearing test** — it proves the sanitizer's
protection (`app/services/sanitize.py`) actually reaches this NEW public
surface, not just the admin read-back `tests/test_blog.py`'s own proof
already covers."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.api.routers.admin import reset_admin_rate_limit_store_for_tests

from .test_auth import _CapturingEmailSender, _make_auth_client
from .test_blog import _admin_headers, _create_post

_SIMPLE_DOC = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "hello"}]}]}


@pytest.fixture()
def email_sender() -> _CapturingEmailSender:
    return _CapturingEmailSender()


@pytest.fixture()
def auth_client(make_client: Callable[..., TestClient], email_sender: _CapturingEmailSender) -> TestClient:
    """Same `make_client`-backed app boot `tests/test_blog.py`'s own
    identically-named fixture uses — the admin-side helpers this module
    borrows (`_admin_headers`, `_create_post`) need a real, non-`client`-
    fixture app instance (see `tests/test_auth.py`'s `_make_auth_client`)."""
    return _make_auth_client(make_client, email_sender)


@pytest.fixture(autouse=True)
def _reset_admin_rate_limit() -> None:
    """Same test-isolation rationale as `tests/test_blog.py`'s identically-
    named fixture — every test in this module that needs a post in a
    particular state drives it through `/admin/blog/posts*`, sharing that
    same module-level admin bucket (`app/api/routers/admin.py`)."""
    reset_admin_rate_limit_store_for_tests()


def _publish(client: TestClient, headers: dict, post_id: str) -> dict:
    response = client.post(f"/admin/blog/posts/{post_id}/publish", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# No auth required
# ---------------------------------------------------------------------------


def test_list_requires_no_auth(client: TestClient) -> None:
    response = client.get("/blog/posts")
    assert response.status_code == 200, response.text


def test_detail_requires_no_auth_for_an_unknown_slug(client: TestClient) -> None:
    response = client.get("/blog/posts/nope")
    assert response.status_code == 404, response.text


# ---------------------------------------------------------------------------
# Published posts are served
# ---------------------------------------------------------------------------


def test_published_post_is_served_by_list_and_detail(auth_client: TestClient) -> None:
    headers = _admin_headers(auth_client)
    created = _create_post(auth_client, headers, title="Published Post")
    _publish(auth_client, headers, created["id"])

    list_response = auth_client.get("/blog/posts")
    assert list_response.status_code == 200, list_response.text
    slugs = {item["slug"] for item in list_response.json()["items"]}
    assert created["slug"] in slugs

    detail_response = auth_client.get(f"/blog/posts/{created['slug']}")
    assert detail_response.status_code == 200, detail_response.text
    body = detail_response.json()
    assert body["slug"] == created["slug"]
    assert body["title"] == "Published Post"
    assert body["body_html"] == "<p>Hello <strong>world</strong></p>"


def test_public_summary_shape_has_no_body_and_no_status(auth_client: TestClient) -> None:
    headers = _admin_headers(auth_client)
    created = _create_post(auth_client, headers, title="Shape Check")
    _publish(auth_client, headers, created["id"])

    response = auth_client.get("/blog/posts")
    assert response.status_code == 200, response.text
    item = next(item for item in response.json()["items"] if item["slug"] == created["slug"])
    assert "body_json" not in item
    assert "body_html" not in item
    assert "status" not in item
    assert set(item.keys()) == {"id", "title", "slug", "excerpt", "published_at", "author_id", "created_at"}


def test_public_detail_never_has_body_json(auth_client: TestClient) -> None:
    headers = _admin_headers(auth_client)
    created = _create_post(auth_client, headers)
    _publish(auth_client, headers, created["id"])

    response = auth_client.get(f"/blog/posts/{created['slug']}")
    assert response.status_code == 200, response.text
    assert "body_json" not in response.json()


def test_excerpt_is_derived_plain_text_from_body_html(auth_client: TestClient) -> None:
    headers = _admin_headers(auth_client)
    created = _create_post(
        auth_client,
        headers,
        title="Excerpt Check",
        body_html="<p>Hello <strong>world</strong>, this is the body.</p>",
    )
    _publish(auth_client, headers, created["id"])

    response = auth_client.get("/blog/posts")
    item = next(item for item in response.json()["items"] if item["slug"] == created["slug"])
    assert item["excerpt"] == "Hello world, this is the body."
    assert "<" not in item["excerpt"]


def test_excerpt_is_none_for_a_body_that_strips_to_nothing(auth_client: TestClient) -> None:
    headers = _admin_headers(auth_client)
    created = _create_post(auth_client, headers, title="Empty Excerpt", body_html="<hr>")
    _publish(auth_client, headers, created["id"])

    response = auth_client.get("/blog/posts")
    item = next(item for item in response.json()["items"] if item["slug"] == created["slug"])
    assert item["excerpt"] is None


# ---------------------------------------------------------------------------
# Draft and soft-deleted posts are never served
# ---------------------------------------------------------------------------


def test_draft_post_is_excluded_from_the_public_list(auth_client: TestClient) -> None:
    headers = _admin_headers(auth_client)
    draft = _create_post(auth_client, headers, title="Still A Draft")

    response = auth_client.get("/blog/posts")
    assert response.status_code == 200, response.text
    slugs = {item["slug"] for item in response.json()["items"]}
    assert draft["slug"] not in slugs


def test_draft_posts_slug_404s_identically_to_an_unknown_slug(auth_client: TestClient) -> None:
    headers = _admin_headers(auth_client)
    draft = _create_post(auth_client, headers, title="Secret Post", slug="secret-post")

    draft_response = auth_client.get(f"/blog/posts/{draft['slug']}")
    unknown_response = auth_client.get("/blog/posts/this-slug-does-not-exist")

    assert draft_response.status_code == 404, draft_response.text
    assert unknown_response.status_code == 404, unknown_response.text
    draft_body, unknown_body = draft_response.json(), unknown_response.json()
    # Same shape/code (the byte-level message text legitimately echoes back
    # whichever slug was requested, so it differs between the two cases —
    # that's not an oracle, both templates are IDENTICAL: "Blog post
    # '{slug}' was not found."). The one thing that would actually be an
    # oracle — the message mentioning "draft"/"unpublished"/any hint the
    # slug secretly belongs to a real, non-public post — is explicitly
    # absent from both.
    assert draft_body.keys() == unknown_body.keys() == {"error"}
    assert draft_body["error"].keys() == unknown_body["error"].keys()
    assert draft_body["error"]["code"] == unknown_body["error"]["code"] == "not_found"
    assert draft_body["error"]["message"] == f"Blog post '{draft['slug']}' was not found."
    assert unknown_body["error"]["message"] == "Blog post 'this-slug-does-not-exist' was not found."
    for message in (draft_body["error"]["message"], unknown_body["error"]["message"]):
        assert "draft" not in message.lower()
        assert "unpublish" not in message.lower()


def test_soft_deleted_post_is_excluded_from_list_and_detail_404s(auth_client: TestClient) -> None:
    headers = _admin_headers(auth_client)
    created = _create_post(auth_client, headers, title="Will Be Deleted")
    _publish(auth_client, headers, created["id"])

    delete_response = auth_client.delete(f"/admin/blog/posts/{created['id']}", headers=headers)
    assert delete_response.status_code == 204, delete_response.text

    list_response = auth_client.get("/blog/posts")
    slugs = {item["slug"] for item in list_response.json()["items"]}
    assert created["slug"] not in slugs

    detail_response = auth_client.get(f"/blog/posts/{created['slug']}")
    assert detail_response.status_code == 404, detail_response.text


def test_unpublished_post_reverts_to_hidden_from_the_public_surface(auth_client: TestClient) -> None:
    headers = _admin_headers(auth_client)
    created = _create_post(auth_client, headers, title="Published Then Unpublished")
    _publish(auth_client, headers, created["id"])
    assert auth_client.get(f"/blog/posts/{created['slug']}").status_code == 200

    unpublish_response = auth_client.post(f"/admin/blog/posts/{created['id']}/unpublish", headers=headers)
    assert unpublish_response.status_code == 200, unpublish_response.text

    response = auth_client.get(f"/blog/posts/{created['slug']}")
    assert response.status_code == 404, response.text


# ---------------------------------------------------------------------------
# THE end-to-end stored-XSS proof (public read of the already-sanitized value)
# ---------------------------------------------------------------------------


def test_public_detail_serves_sanitized_html_not_the_raw_xss_payload(auth_client: TestClient) -> None:
    headers = _admin_headers(auth_client)
    raw_html = (
        "<p>Intro paragraph with <strong>bold</strong> text.</p>"
        '<a href="javascript:alert(1)">click me</a>'
        "<img src=x onerror=alert(1)>"
        "<script>alert(1)</script>"
        '<p onclick="alert(1)">click handler</p>'
        '<a href="https://example.com" title="Example">safe link</a>'
    )
    created = _create_post(auth_client, headers, title="Public XSS Test", body_html=raw_html)
    _publish(auth_client, headers, created["id"])

    response = auth_client.get(f"/blog/posts/{created['slug']}")
    assert response.status_code == 200, response.text
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

    # The excerpt (derived from the same already-sanitized body_html) is
    # also clean plain text -- no leaked markup or payload text.
    list_response = auth_client.get("/blog/posts")
    item = next(item for item in list_response.json()["items"] if item["slug"] == created["slug"])
    assert "<" not in item["excerpt"]
    assert "alert(1)" not in item["excerpt"]


# ---------------------------------------------------------------------------
# Pagination + newest-first ordering
# ---------------------------------------------------------------------------


def test_list_paginates_and_orders_newest_first_by_published_at(auth_client: TestClient) -> None:
    headers = _admin_headers(auth_client)
    first = _create_post(auth_client, headers, title="First Published")
    _publish(auth_client, headers, first["id"])
    second = _create_post(auth_client, headers, title="Second Published")
    _publish(auth_client, headers, second["id"])
    third = _create_post(auth_client, headers, title="Third Published")
    _publish(auth_client, headers, third["id"])

    response = auth_client.get("/blog/posts", params={"page": 1, "size": 2})
    assert response.status_code == 200, response.text
    body = response.json()
    assert {"items", "total", "page", "size", "pages"} <= body.keys()
    assert body["size"] == 2
    assert body["total"] >= 3
    slugs_page_1 = [item["slug"] for item in body["items"]]
    assert slugs_page_1[0] == third["slug"]  # newest published_at first
    assert slugs_page_1[1] == second["slug"]

    page_2 = auth_client.get("/blog/posts", params={"page": 2, "size": 2})
    assert page_2.status_code == 200, page_2.text
    slugs_page_2 = [item["slug"] for item in page_2.json()["items"]]
    assert first["slug"] in slugs_page_2


def test_list_size_is_bounded_by_the_pagination_components_cap(auth_client: TestClient) -> None:
    response = auth_client.get("/blog/posts", params={"size": 500})
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "validation_failed"
