"""Stage 13d (deferred acceptance item, issue #54): the PUBLIC, UNAUTHENTICATED
blog read surface — `GET /blog/posts` and `GET /blog/posts/{slug}` — the
render surface `app/services/sanitize.py`'s stored-XSS sanitizer was built
to protect. NOT under `/admin`, NO `require_admin`/`require_roles`
dependency of any kind — same "public by construction, not by omission"
posture `app/api/routers/items.py`'s own module docstring documents for
`Item`: every route below is intentionally public, not merely undecorated.

**Visibility rule, the one thing this whole module exists to enforce**:
both routes serve ONLY rows where `status == "published"` AND
`BlogPost.not_deleted()` — a `"draft"` post's slug on `GET /blog/posts/
{slug}` renders the IDENTICAL 404 `ErrorEnvelope` a genuinely nonexistent
slug does (same message shape, same `not_found` code — no draft-existence
oracle: a caller cannot distinguish "this slug was never used" from "this
slug belongs to an unpublished post" from the response alone), and the
list endpoint excludes both cases outright rather than filtering them out
of a client-visible page. `published_at <= now()` is ALSO required
(defense-in-depth for a hypothetical future `published_at` set ahead of
time — see this module's own note below on why `scheduled` itself is
deferred, not built, in this pass) — today's only write path
(`app/api/routers/blog.py`'s `publish_admin_blog_post`) always stamps
`published_at=utc_now()` at publish time, so this condition is a no-op
against every post this app can currently produce, not a behavior change.

**`body_json` is impossible to get from either response — enforced by the
response schema, not by a per-field omission at the call site.**
`PublicBlogPostSummaryOut`/`PublicBlogPostOut` (`app/schemas/blog.py`) are
NEW schemas, not `BlogPostSummaryOut`/`BlogPostOut` (the ADMIN shapes)
reused with a field dropped — there is no `body_json` attribute anywhere
in either public schema's `model_fields` for a mapping bug to accidentally
surface; FastAPI's `response_model` would reject a response containing an
undeclared field before it ever serialized, so even a wrong ORM->schema
mapping here could not leak it. `body_html` on the detail response is
ALWAYS the value already sanitized by `app/services/sanitize.py:
sanitize_blog_html()` at write time (`app/api/routers/blog.py`'s create/
update handlers) — this module never re-sanitizes, and never reads
`body_json` off the ORM row at all.

**Rate limiting**: deliberately NOT `app/api/routers/admin.py`'s
`require_admin_rate_limit` dependency (that bucket is reserved for the
privileged `/admin/*` surface — see this module's own registration
comment in `app/main.py`) — this router relies on the SAME whole-app,
general per-IP `RateLimitMiddleware` ceiling (`app/core/security/
rate_limiting`, wired in `app/main.py`'s `create_app()`) every other
public route (`items`, `health`) already runs behind, matching this
stage's own "keep the existing per-IP ceiling, do NOT put them on the
tighter admin bucket" instruction.

**`scheduled` status — deferred, not built, in this pass.** The Stage 13d
plan's smaller acceptance item ("scheduled posts are not served before
their time") needs the ADMIN publish path (`app/api/routers/blog.py`'s
`publish_admin_blog_post`) to accept an optional future `published_at` —
that write-path change is explicitly out of scope for this change (see
this module's own docstring header: "Do NOT touch the admin endpoints").
Building `scheduled` without a way to ever reach it from any write path
would be dead code, not a real feature — so it's deferred whole, not
half-built. The `published_at <= now()` guard above is still applied,
defensively, so wiring `scheduled` in later is an ADDITIVE change to the
admin write path alone; this read-side query already tolerates it."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import Page, PageParams, get_db, paginate_select
from app.core.errors import ErrorEnvelope, NotFoundError
from app.core.security.auth.stores import utc_now
from app.models.blog_post import BlogPost
from app.schemas.blog import (
    BlogPostStatus,
    PublicBlogPostOut,
    PublicBlogPostSummaryOut,
    derive_excerpt,
)

router = APIRouter(prefix="/blog", tags=["blog"])

_POST_NOT_FOUND_RESPONSE = {404: {"model": ErrorEnvelope, "description": "Blog post not found."}}


def _visible_filters() -> tuple:
    """The ONE visibility predicate both routes below share — see this
    module's own docstring for the full rationale (published + not
    soft-deleted + not scheduled-into-the-future). A `tuple`, not a
    generator, so it can be splatted into a SQLAlchemy `.where(*filters)`
    call more than once without exhaustion."""
    return (
        BlogPost.not_deleted(),
        BlogPost.status == BlogPostStatus.PUBLISHED.value,
        BlogPost.published_at.is_not(None),
        BlogPost.published_at <= utc_now(),
    )


def _to_public_summary_out(post: BlogPost) -> PublicBlogPostSummaryOut:
    """Explicit field-by-field construction, NOT `PublicBlogPostSummaryOut.
    model_validate(post)` — `excerpt` (`app/schemas/blog.py`'s
    `derive_excerpt`) has no matching `BlogPost` column for `from_
    attributes` to read off the ORM row, so this mapping is spelled out by
    hand rather than leaning on Pydantic's attribute-reflection path."""
    return PublicBlogPostSummaryOut(
        id=post.id,
        title=post.title,
        slug=post.slug,
        excerpt=derive_excerpt(post.body_html),
        published_at=post.published_at,
        author_id=post.author_id,
        created_at=post.created_at,
    )


def _to_public_detail_out(post: BlogPost) -> PublicBlogPostOut:
    return PublicBlogPostOut(
        id=post.id,
        title=post.title,
        slug=post.slug,
        excerpt=derive_excerpt(post.body_html),
        published_at=post.published_at,
        author_id=post.author_id,
        created_at=post.created_at,
        body_html=post.body_html,
    )


@router.get(
    "/posts",
    response_model=Page[PublicBlogPostSummaryOut],
    summary="List blog posts (public)",
    operation_id="list_public_blog_posts_blog_posts_get",
)
async def list_public_blog_posts(
    params: PageParams = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Page[PublicBlogPostSummaryOut]:
    """Newest-first by `published_at` — NOT `AsyncRepository.list()`
    (which has no ordering hook of its own; see `app/core/db/repository.py`'s
    own docstring), so this builds the `select()` directly and hands it to
    `paginate_select()` (the same internal helper `AsyncRepository.list()`
    itself delegates to) rather than reusing that wrapper. `?page=`/`?size=`
    bounds are `PageParams`'s own (`app/core/db/schema.py`: `size` capped at
    200) — no separate, looser cap for this public surface."""
    stmt = select(BlogPost).where(*_visible_filters()).order_by(BlogPost.published_at.desc())
    result = await paginate_select(db, stmt, params)
    mapped = [_to_public_summary_out(post) for post in result.items]
    return Page.create(mapped, total=result.total, params=params)


@router.get(
    "/posts/{slug}",
    response_model=PublicBlogPostOut,
    summary="Get blog post (public)",
    operation_id="get_public_blog_post_blog_posts__slug__get",
    responses=_POST_NOT_FOUND_RESPONSE,
)
async def get_public_blog_post(
    slug: str,
    db: AsyncSession = Depends(get_db),
) -> PublicBlogPostOut:
    """A draft or soft-deleted post's slug 404s IDENTICALLY to an unknown
    slug — see this module's own docstring, "no draft-existence oracle".
    `slug` is a plain `str` path param (not further validated against
    `SLUG_PATTERN` here) — an invalid-shaped slug simply can never match
    any row's `slug` column, so it falls straight through to the same 404
    a well-shaped-but-unknown slug gets; a 422 here would itself leak one
    more bit of information (shape-valid vs shape-invalid) a public 404
    should not distinguish."""
    stmt = select(BlogPost).where(*_visible_filters(), BlogPost.slug == slug)
    result = await db.execute(stmt)
    post = result.scalar_one_or_none()
    if post is None:
        raise NotFoundError(f"Blog post '{slug}' was not found.")
    return _to_public_detail_out(post)
