"""Stage 13d — the blog/CMS admin surface, over real HTTP against
`APIClient`. The DRF counterpart to `backend/fastapi`'s `tests/
test_blog.py` -- same test names/scenarios/payloads, ported to this
block's `email_sender`/`_register_and_verify`/`_login` helpers (`.test_auth`)
and `seed_admin` (`core.security.auth.stores`, `tests/test_admin_users.py`'s
own `_seed_verified_admin` precedent).

**The stored-XSS proof
(`test_create_stores_only_sanitized_html_stripping_every_xss_payload`,
`test_update_re_sanitizes_body_html`) is THE load-bearing test in this
module** -- identical payload matrix and identical assertions to the
FastAPI track's own test of the same name; a divergence between the two
is a PARITY BUG, not a style choice.

`@pytest.mark.django_db(transaction=True)` module-wide -- same rationale
`tests/test_admin_users.py`'s own module docstring documents in full."""

from __future__ import annotations

import logging
import uuid

import pytest
from asgiref.sync import async_to_sync
from rest_framework.test import APIClient

from core.models import Comment, User
from core.security.auth.stores import seed_admin

from .test_auth import (  # noqa: F401
    _CapturingEmailSender,
    _login,
    _register_and_verify,
    email_sender,
)

pytestmark = pytest.mark.django_db(transaction=True)

_ADMIN_EMAIL = "admin@example.com"
_ADMIN_PASSWORD = "correct horse battery staple 2"
_EMAIL = "alice@example.com"
_PASSWORD = "correct horse battery staple"

_SOME_ID = "00000000-0000-0000-0000-000000000000"

_SIMPLE_DOC = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "hello"}]}]}


def _seed_verified_admin(email: str, password: str) -> str:
    user = async_to_sync(seed_admin)(email, password)
    User.objects.filter(email=email).update(email_verified=True)
    return user.id


def _admin_headers(client: APIClient, email: str = _ADMIN_EMAIL, password: str = _ADMIN_PASSWORD) -> dict:
    _seed_verified_admin(email, password)
    tokens = _login(client, email, password)
    return {"HTTP_AUTHORIZATION": f"Bearer {tokens['access_token']}"}


def _create_post(client: APIClient, headers: dict, **overrides: object) -> dict:
    payload = {
        "title": "Hello World",
        "body_json": _SIMPLE_DOC,
        "body_html": "<p>Hello <strong>world</strong></p>",
        **overrides,
    }
    response = client.post("/admin/blog/posts", payload, format="json", **headers)
    assert response.status_code == 201, response.content
    return response.json()


# ---------------------------------------------------------------------------
# 401 / 403 across every /admin/blog/* endpoint
# ---------------------------------------------------------------------------

_ENDPOINTS: list[tuple[str, str, dict | None]] = [
    ("get", "/admin/blog/posts", None),
    ("post", "/admin/blog/posts", {"title": "x", "body_json": _SIMPLE_DOC, "body_html": "<p>x</p>"}),
    ("get", f"/admin/blog/posts/{_SOME_ID}", None),
    ("patch", f"/admin/blog/posts/{_SOME_ID}", {"title": "y"}),
    ("post", f"/admin/blog/posts/{_SOME_ID}/publish", None),
    ("post", f"/admin/blog/posts/{_SOME_ID}/unpublish", None),
    ("delete", f"/admin/blog/posts/{_SOME_ID}", None),
    ("get", "/admin/blog/comments", None),
    ("post", f"/admin/blog/comments/{_SOME_ID}/hide", None),
    ("delete", f"/admin/blog/comments/{_SOME_ID}", None),
]


@pytest.mark.parametrize("method,path,body", _ENDPOINTS)
def test_every_blog_endpoint_returns_401_for_anonymous(
    api_client: APIClient, method: str, path: str, body: dict | None
) -> None:
    response = getattr(api_client, method)(path, body, format="json")
    assert response.status_code == 401, response.content
    assert response.json()["error"]["code"] == "unauthenticated"


@pytest.mark.parametrize("method,path,body", _ENDPOINTS)
def test_every_blog_endpoint_returns_403_for_a_non_admin(
    api_client: APIClient, email_sender: _CapturingEmailSender, method: str, path: str, body: dict | None
) -> None:
    _register_and_verify(api_client, email_sender)
    tokens = _login(api_client, _EMAIL, _PASSWORD)
    headers = {"HTTP_AUTHORIZATION": f"Bearer {tokens['access_token']}"}
    response = getattr(api_client, method)(path, body, format="json", **headers)
    assert response.status_code == 403, response.content
    assert response.json()["error"]["code"] == "permission_denied"


# ---------------------------------------------------------------------------
# THE stored-XSS proof
# ---------------------------------------------------------------------------


def test_create_stores_only_sanitized_html_stripping_every_xss_payload(api_client: APIClient) -> None:
    """Identical payload matrix and identical assertions to `backend/
    fastapi`'s test of the same name -- see that module's own docstring."""
    headers = _admin_headers(api_client)
    raw_html = (
        '<p>Intro paragraph with <strong>bold</strong> text.</p>'
        '<a href="javascript:alert(1)">click me</a>'
        '<a href="data:text/html,alert(1)">data link</a>'
        '<img src=x onerror=alert(1)>'
        "<script>alert(1)</script>"
        '<iframe src="javascript:alert(1)"></iframe>'
        '<p style="expression(alert(1))">styled</p>'
        "<svg onload=alert(1)></svg>"
        '<p onclick="alert(1)">click handler</p>'
        '<object data="evil.swf"></object>'
        '<a href="https://example.com" title="Example">safe link</a>'
    )
    created = _create_post(api_client, headers, title="XSS Test Post", body_html=raw_html)

    response = api_client.get(f"/admin/blog/posts/{created['id']}", **headers)
    assert response.status_code == 200, response.content
    stored_html = response.json()["body_html"]

    assert "javascript:" not in stored_html
    assert "data:text/html" not in stored_html
    assert "onerror" not in stored_html
    assert "onclick" not in stored_html
    assert "onload" not in stored_html
    assert "<script" not in stored_html
    assert "</script>" not in stored_html
    assert "alert(1)" not in stored_html.replace("XSS Test Post", "")
    assert "<iframe" not in stored_html
    assert "<svg" not in stored_html
    assert "<img" not in stored_html
    assert "style=" not in stored_html
    assert "<object" not in stored_html

    assert "<p>Intro paragraph with <strong>bold</strong> text.</p>" in stored_html
    assert '<a href="https://example.com" title="Example" rel="noopener noreferrer nofollow">safe link</a>' in (
        stored_html
    )


def test_update_re_sanitizes_body_html(api_client: APIClient) -> None:
    headers = _admin_headers(api_client)
    created = _create_post(api_client, headers)

    response = api_client.patch(
        f"/admin/blog/posts/{created['id']}",
        {"body_html": '<p>updated</p><script>alert(1)</script><a href="javascript:alert(2)">x</a>'},
        format="json",
        **headers,
    )
    assert response.status_code == 200, response.content
    stored_html = response.json()["body_html"]
    assert "<script" not in stored_html
    assert "javascript:" not in stored_html
    assert "<p>updated</p>" in stored_html


# ---------------------------------------------------------------------------
# Create — happy paths, slug handling, validation
# ---------------------------------------------------------------------------


def test_create_without_slug_derives_one_from_title(api_client: APIClient) -> None:
    headers = _admin_headers(api_client)
    created = _create_post(api_client, headers, title="Hello, World! Édition")
    assert created["slug"].startswith("hello-world")
    assert created["status"] == "draft"
    assert created["published_at"] is None
    assert created["body_json"] == _SIMPLE_DOC


def test_create_with_explicit_slug(api_client: APIClient) -> None:
    headers = _admin_headers(api_client)
    created = _create_post(api_client, headers, slug="my-custom-slug")
    assert created["slug"] == "my-custom-slug"


def test_create_derived_slug_auto_disambiguates_on_collision(api_client: APIClient) -> None:
    headers = _admin_headers(api_client)
    first = _create_post(api_client, headers, title="Same Title")
    second = _create_post(api_client, headers, title="Same Title")
    assert first["slug"] != second["slug"]
    assert second["slug"].startswith(first["slug"])


def test_create_with_explicit_duplicate_slug_is_a_conflict(api_client: APIClient) -> None:
    headers = _admin_headers(api_client)
    _create_post(api_client, headers, slug="taken-slug")
    response = api_client.post(
        "/admin/blog/posts",
        {"title": "Another", "slug": "taken-slug", "body_json": _SIMPLE_DOC, "body_html": "<p>x</p>"},
        format="json",
        **headers,
    )
    assert response.status_code == 409, response.content
    assert response.json()["error"]["code"] == "conflict"


def test_create_with_two_active_duplicate_slugs_is_still_a_conflict(api_client: APIClient) -> None:
    """Companion to `test_create_with_explicit_duplicate_slug_is_a_conflict`
    above -- TWO ACTIVE posts can never share a slug (409), but ONE active
    post reusing a SOFT-DELETED post's slug succeeds cleanly (201, see
    `test_create_reusing_a_soft_deleted_posts_slug_succeeds` below). Byte-
    identical scenario to `backend/fastapi`'s test of the same name."""
    headers = _admin_headers(api_client)
    _create_post(api_client, headers, slug="dup-slug")
    response = api_client.post(
        "/admin/blog/posts",
        {"title": "Second", "slug": "dup-slug", "body_json": _SIMPLE_DOC, "body_html": "<p>x</p>"},
        format="json",
        **headers,
    )
    assert response.status_code == 409, response.content
    assert response.json()["error"]["code"] == "conflict"


def test_create_reusing_a_soft_deleted_posts_slug_succeeds(api_client: APIClient) -> None:
    """THE partial-unique-constraint proof -- byte-identical scenario to
    `backend/fastapi`'s test of the same name: create `foo`, soft-delete
    it, then create ANOTHER `foo`. Before the DB-level
    `uq_blog_posts_slug_active` partial unique constraint (`core/
    models.py`), the OLD full-table unique constraint on `slug` disagreed
    with `_slug_taken`'s soft-delete-scoped friendly check and this INSERT
    raised an unenveloped 500 (`IntegrityError`). Now a clean 201, not a
    500 -- and not a 409 either."""
    headers = _admin_headers(api_client)
    first = _create_post(api_client, headers, slug="reusable-slug")

    delete_response = api_client.delete(f"/admin/blog/posts/{first['id']}", **headers)
    assert delete_response.status_code == 204, delete_response.content

    second = _create_post(api_client, headers, slug="reusable-slug")
    assert second["slug"] == "reusable-slug"
    assert second["id"] != first["id"]


def test_create_with_invalid_slug_shape_is_a_422(api_client: APIClient) -> None:
    headers = _admin_headers(api_client)
    response = api_client.post(
        "/admin/blog/posts",
        {
            "title": "Bad Slug",
            "slug": "Not A Valid Slug!",
            "body_json": _SIMPLE_DOC,
            "body_html": "<p>x</p>",
        },
        format="json",
        **headers,
    )
    assert response.status_code == 422, response.content
    assert response.json()["error"]["code"] == "validation_failed"


def test_create_with_body_html_over_the_size_cap_is_a_422(api_client: APIClient) -> None:
    """`core/serializers.py`'s `_BODY_HTML_MAX_CHARS` (1,000,000) defense-
    in-depth cap -- byte-identical scenario/cap value to `backend/fastapi`'s
    test of the same name."""
    headers = _admin_headers(api_client)
    oversized_html = "<p>" + ("x" * 1_000_000) + "</p>"
    response = api_client.post(
        "/admin/blog/posts",
        {"title": "Too Big", "body_json": _SIMPLE_DOC, "body_html": oversized_html},
        format="json",
        **headers,
    )
    assert response.status_code == 422, response.content
    assert response.json()["error"]["code"] == "validation_failed"


def test_create_with_body_json_over_the_size_cap_is_a_422(api_client: APIClient) -> None:
    """`core/serializers.py`'s `_BODY_JSON_MAX_SERIALIZED_CHARS`
    (1,000,000) defense-in-depth cap, enforced on the SERIALIZED
    (`json.dumps`) size via `validate_body_json`/`_validate_body_json_size`
    -- byte-identical scenario/cap value to `backend/fastapi`'s test of the
    same name."""
    headers = _admin_headers(api_client)
    oversized_doc = {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "x" * 1_100_000}]}],
    }
    response = api_client.post(
        "/admin/blog/posts",
        {"title": "Too Big", "body_json": oversized_doc, "body_html": "<p>x</p>"},
        format="json",
        **headers,
    )
    assert response.status_code == 422, response.content
    assert response.json()["error"]["code"] == "validation_failed"


def test_create_with_body_html_at_normal_size_still_works(api_client: APIClient) -> None:
    headers = _admin_headers(api_client)
    normal_html = "<p>" + ("hello world " * 100) + "</p>"
    created = _create_post(api_client, headers, title="Normal Size", body_html=normal_html)
    assert created["body_html"].startswith("<p>hello world")


def test_create_rejects_an_unknown_field(api_client: APIClient) -> None:
    """Parity with the FastAPI track's `BlogPostCreate`
    (`ConfigDict(extra="forbid")`) -- an unknown top-level key in the
    request body 422s the same way on both backends."""
    headers = _admin_headers(api_client)
    response = api_client.post(
        "/admin/blog/posts",
        {"title": "x", "body_json": _SIMPLE_DOC, "body_html": "<p>x</p>", "is_featured": True},
        format="json",
        **headers,
    )
    assert response.status_code == 422, response.content
    assert response.json()["error"]["code"] == "validation_failed"


def test_create_and_audit(api_client: APIClient, caplog: pytest.LogCaptureFixture) -> None:
    headers = _admin_headers(api_client)
    with caplog.at_level(logging.INFO, logger="audit"):
        created = _create_post(api_client, headers)
    assert any('"action": "admin.blog.create"' in r.message for r in caplog.records)
    assert any(f'"resource": "blog_post:{created["id"]}"' in r.message for r in caplog.records)
    assert any('"outcome": "success"' in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Get / list
# ---------------------------------------------------------------------------


def test_get_post_returns_404_for_an_unknown_id(api_client: APIClient) -> None:
    headers = _admin_headers(api_client)
    response = api_client.get(f"/admin/blog/posts/{_SOME_ID}", **headers)
    assert response.status_code == 404, response.content
    assert response.json()["error"]["code"] == "not_found"


def test_get_post_returns_404_for_a_malformed_id(api_client: APIClient) -> None:
    headers = _admin_headers(api_client)
    response = api_client.get("/admin/blog/posts/not-a-uuid", **headers)
    assert response.status_code == 404, response.content
    assert response.json()["error"]["code"] == "not_found"


def test_list_posts_summary_shape_omits_bodies_and_paginates(api_client: APIClient) -> None:
    headers = _admin_headers(api_client)
    _create_post(api_client, headers, title="Post One")
    _create_post(api_client, headers, title="Post Two")

    response = api_client.get("/admin/blog/posts", **headers)
    assert response.status_code == 200, response.content
    body = response.json()
    assert {"items", "total", "page", "size", "pages"} <= body.keys()
    assert body["total"] >= 2
    for item in body["items"]:
        assert "body_html" not in item
        assert "body_json" not in item


def test_list_posts_filters_by_status(api_client: APIClient) -> None:
    headers = _admin_headers(api_client)
    created = _create_post(api_client, headers, title="Published Post")
    api_client.post(f"/admin/blog/posts/{created['id']}/publish", **headers)
    _create_post(api_client, headers, title="Still Draft")

    response = api_client.get("/admin/blog/posts", {"status": "published"}, **headers)
    assert response.status_code == 200, response.content
    body = response.json()
    titles = {item["title"] for item in body["items"]}
    assert "Published Post" in titles
    assert "Still Draft" not in titles


def test_list_posts_rejects_unknown_status_filter(api_client: APIClient) -> None:
    headers = _admin_headers(api_client)
    response = api_client.get("/admin/blog/posts", {"status": "archived"}, **headers)
    assert response.status_code == 422, response.content
    assert response.json()["error"]["code"] == "validation_failed"


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def test_update_happy_path_partial(api_client: APIClient) -> None:
    headers = _admin_headers(api_client)
    created = _create_post(api_client, headers)

    response = api_client.patch(
        f"/admin/blog/posts/{created['id']}", {"title": "New Title"}, format="json", **headers
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["title"] == "New Title"
    assert body["slug"] == created["slug"]


def test_update_to_a_taken_slug_is_a_conflict(api_client: APIClient) -> None:
    headers = _admin_headers(api_client)
    _create_post(api_client, headers, slug="slug-a")
    other = _create_post(api_client, headers, slug="slug-b")

    response = api_client.patch(
        f"/admin/blog/posts/{other['id']}", {"slug": "slug-a"}, format="json", **headers
    )
    assert response.status_code == 409, response.content
    assert response.json()["error"]["code"] == "conflict"


def test_update_to_the_same_slug_is_not_a_conflict(api_client: APIClient) -> None:
    headers = _admin_headers(api_client)
    created = _create_post(api_client, headers, slug="unchanged-slug")

    response = api_client.patch(
        f"/admin/blog/posts/{created['id']}", {"slug": "unchanged-slug"}, format="json", **headers
    )
    assert response.status_code == 200, response.content


def test_update_with_explicit_null_title_is_a_422(api_client: APIClient) -> None:
    headers = _admin_headers(api_client)
    created = _create_post(api_client, headers)

    response = api_client.patch(
        f"/admin/blog/posts/{created['id']}", {"title": None}, format="json", **headers
    )
    assert response.status_code == 422, response.content
    assert response.json()["error"]["code"] == "validation_failed"


def test_update_returns_404_for_an_unknown_id(api_client: APIClient) -> None:
    headers = _admin_headers(api_client)
    response = api_client.patch(f"/admin/blog/posts/{_SOME_ID}", {"title": "x"}, format="json", **headers)
    assert response.status_code == 404, response.content


def test_update_with_body_html_over_the_size_cap_is_a_422(api_client: APIClient) -> None:
    headers = _admin_headers(api_client)
    created = _create_post(api_client, headers)

    oversized_html = "<p>" + ("x" * 1_000_000) + "</p>"
    response = api_client.patch(
        f"/admin/blog/posts/{created['id']}", {"body_html": oversized_html}, format="json", **headers
    )
    assert response.status_code == 422, response.content
    assert response.json()["error"]["code"] == "validation_failed"


def test_update_with_body_json_over_the_size_cap_is_a_422(api_client: APIClient) -> None:
    headers = _admin_headers(api_client)
    created = _create_post(api_client, headers)

    oversized_doc = {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "x" * 1_100_000}]}],
    }
    response = api_client.patch(
        f"/admin/blog/posts/{created['id']}", {"body_json": oversized_doc}, format="json", **headers
    )
    assert response.status_code == 422, response.content
    assert response.json()["error"]["code"] == "validation_failed"


# ---------------------------------------------------------------------------
# Publish / unpublish
# ---------------------------------------------------------------------------


def test_publish_then_unpublish_happy_path_and_audit(
    api_client: APIClient, caplog: pytest.LogCaptureFixture
) -> None:
    headers = _admin_headers(api_client)
    created = _create_post(api_client, headers)

    with caplog.at_level(logging.INFO, logger="audit"):
        response = api_client.post(f"/admin/blog/posts/{created['id']}/publish", **headers)
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["status"] == "published"
    assert body["published_at"] is not None
    assert any('"action": "admin.blog.publish"' in r.message for r in caplog.records)

    with caplog.at_level(logging.INFO, logger="audit"):
        response = api_client.post(f"/admin/blog/posts/{created['id']}/unpublish", **headers)
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["status"] == "draft"
    assert body["published_at"] is None
    assert any('"action": "admin.blog.unpublish"' in r.message for r in caplog.records)


def test_publish_an_already_published_post_is_a_conflict(api_client: APIClient) -> None:
    headers = _admin_headers(api_client)
    created = _create_post(api_client, headers)
    first = api_client.post(f"/admin/blog/posts/{created['id']}/publish", **headers)
    assert first.status_code == 200, first.content

    response = api_client.post(f"/admin/blog/posts/{created['id']}/publish", **headers)
    assert response.status_code == 409, response.content
    assert response.json()["error"]["code"] == "conflict"


def test_unpublish_a_draft_post_is_a_conflict(api_client: APIClient) -> None:
    headers = _admin_headers(api_client)
    created = _create_post(api_client, headers)

    response = api_client.post(f"/admin/blog/posts/{created['id']}/unpublish", **headers)
    assert response.status_code == 409, response.content
    assert response.json()["error"]["code"] == "conflict"


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_post_soft_deletes_and_audits(api_client: APIClient, caplog: pytest.LogCaptureFixture) -> None:
    headers = _admin_headers(api_client)
    created = _create_post(api_client, headers)

    with caplog.at_level(logging.INFO, logger="audit"):
        response = api_client.delete(f"/admin/blog/posts/{created['id']}", **headers)
    assert response.status_code == 204, response.content
    assert response.content == b""
    assert any('"action": "admin.blog.delete"' in r.message for r in caplog.records)

    follow_up = api_client.get(f"/admin/blog/posts/{created['id']}", **headers)
    assert follow_up.status_code == 404, follow_up.content


# ---------------------------------------------------------------------------
# Comments — list / hide / delete
# ---------------------------------------------------------------------------


def _seed_comment(post_id: str, *, status: str = "visible", body: str = "Nice post!") -> str:
    comment = Comment.objects.create(post_id=uuid.UUID(post_id), author=None, body=body, status=status)
    return str(comment.id)


def test_list_comments_filters_by_post_id_and_status(api_client: APIClient) -> None:
    headers = _admin_headers(api_client)
    post = _create_post(api_client, headers)
    other_post = _create_post(api_client, headers, title="Other")
    comment_id = _seed_comment(post["id"], body="On post one")
    _seed_comment(other_post["id"], body="On post two")
    hidden_id = _seed_comment(post["id"], status="hidden", body="hidden comment")

    response = api_client.get("/admin/blog/comments", {"post_id": post["id"]}, **headers)
    assert response.status_code == 200, response.content
    bodies = {item["body"] for item in response.json()["items"]}
    assert "On post one" in bodies
    assert "On post two" not in bodies
    assert "hidden comment" in bodies

    response = api_client.get(
        "/admin/blog/comments", {"post_id": post["id"], "status": "hidden"}, **headers
    )
    assert response.status_code == 200, response.content
    ids = {item["id"] for item in response.json()["items"]}
    assert ids == {hidden_id}
    assert comment_id not in ids


def test_list_comments_rejects_a_malformed_post_id_filter(api_client: APIClient) -> None:
    headers = _admin_headers(api_client)
    response = api_client.get("/admin/blog/comments", {"post_id": "not-a-uuid"}, **headers)
    assert response.status_code == 422, response.content
    assert response.json()["error"]["code"] == "validation_failed"


def test_hide_comment_happy_path_and_audit(api_client: APIClient, caplog: pytest.LogCaptureFixture) -> None:
    headers = _admin_headers(api_client)
    post = _create_post(api_client, headers)
    comment_id = _seed_comment(post["id"])

    with caplog.at_level(logging.INFO, logger="audit"):
        response = api_client.post(f"/admin/blog/comments/{comment_id}/hide", **headers)
    assert response.status_code == 200, response.content
    assert response.json()["status"] == "hidden"
    assert any('"action": "admin.comment.hide"' in r.message for r in caplog.records)


def test_hide_an_already_hidden_comment_is_a_conflict(api_client: APIClient) -> None:
    headers = _admin_headers(api_client)
    post = _create_post(api_client, headers)
    comment_id = _seed_comment(post["id"], status="hidden")

    response = api_client.post(f"/admin/blog/comments/{comment_id}/hide", **headers)
    assert response.status_code == 409, response.content
    assert response.json()["error"]["code"] == "conflict"


def test_hide_comment_returns_404_for_an_unknown_id(api_client: APIClient) -> None:
    headers = _admin_headers(api_client)
    response = api_client.post(f"/admin/blog/comments/{_SOME_ID}/hide", **headers)
    assert response.status_code == 404, response.content


def test_delete_comment_soft_deletes_and_audits(api_client: APIClient, caplog: pytest.LogCaptureFixture) -> None:
    headers = _admin_headers(api_client)
    post = _create_post(api_client, headers)
    comment_id = _seed_comment(post["id"])

    with caplog.at_level(logging.INFO, logger="audit"):
        response = api_client.delete(f"/admin/blog/comments/{comment_id}", **headers)
    assert response.status_code == 204, response.content
    assert any('"action": "admin.comment.delete"' in r.message for r in caplog.records)

    follow_up = api_client.get("/admin/blog/comments", {"post_id": post["id"]}, **headers)
    ids = {item["id"] for item in follow_up.json()["items"]}
    assert comment_id not in ids
