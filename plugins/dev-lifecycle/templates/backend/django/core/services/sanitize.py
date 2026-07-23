"""Stage 13d: THE stored-XSS defense for the blog/CMS write-path — the
Django-track TWIN of `app/services/sanitize.py` (backend/fastapi). Every
constant and the `sanitize_blog_html()` function body below are BYTE-
IDENTICAL to that module — same `nh3` pin (references/compatibility-
matrix.md's Backend — Python row), same allowlist, same forced `rel`, same
`clean_content_tags`. A divergence between the two is a PARITY BUG, caught
by `tests/test_blog.py`'s stored-XSS proof on this track (and its
identically-named counterpart on the FastAPI track) — see that test module
for the exact payload matrix both backends are proven against.

**The write-path boundary (read this before touching `core/views.py`'s
blog admin views).** `sanitize_blog_html()` below is called BEFORE
`BlogPost.body_html` is ever persisted — a post can NEVER reach the
database with unsanitized HTML. `body_json` is stored OPAQUE, never
sanitized and never rendered anywhere public. **The render rule, stated
plainly: only `body_html` is ever rendered; `body_json` is only reloaded
into the (later, Stage 13d UI) TipTap editor, in the authenticated admin
context.** See `app/services/sanitize.py`'s own docstring for the full
policy rationale (tag/attribute/scheme choices, why `<img>` is absent,
why `script`/`style` are content-stripped) — reproduced here only where
it's this module's own constants, not duplicated prose."""

from __future__ import annotations

import nh3

# --- THE policy (byte-identical to app/services/sanitize.py) -------------

ALLOWED_TAGS: frozenset[str] = frozenset(
    {
        "p",
        "br",
        "h2",
        "h3",
        "h4",
        "strong",
        "em",
        "u",
        "s",
        "blockquote",
        "ul",
        "ol",
        "li",
        "a",
        "code",
        "pre",
        "hr",
    }
)

ALLOWED_ATTRIBUTES: dict[str, frozenset[str]] = {
    "a": frozenset({"href", "title"}),
}

ALLOWED_URL_SCHEMES: frozenset[str] = frozenset({"https", "http", "mailto"})

LINK_REL: str = "noopener noreferrer nofollow"

CLEAN_CONTENT_TAGS: frozenset[str] = frozenset({"script", "style"})


def sanitize_blog_html(raw_html: str) -> str:
    """THE write-path boundary function — see module docstring. Byte-
    identical body to `app/services/sanitize.py`'s own function."""
    return nh3.clean(
        raw_html,
        tags=set(ALLOWED_TAGS),
        attributes={tag: set(attrs) for tag, attrs in ALLOWED_ATTRIBUTES.items()},
        url_schemes=set(ALLOWED_URL_SCHEMES),
        link_rel=LINK_REL,
        clean_content_tags=set(CLEAN_CONTENT_TAGS),
        strip_comments=True,
    )
