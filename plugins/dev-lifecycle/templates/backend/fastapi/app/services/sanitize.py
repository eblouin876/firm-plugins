"""Stage 13d: THE stored-XSS defense for the blog/CMS write-path — a
single, narrow allowlist HTML sanitizer built on `nh3` (Rust/`ammonia`
bindings, pinned per references/compatibility-matrix.md's Backend —
Python row). This module owns exactly one policy decision, encoded once
as module-level constants so the Django track (`core/services/
sanitize.py`) can mirror it byte-for-byte — see that module's own
docstring for the parity contract, and `tests/test_blog.py`'s stored-XSS
proof for the test that catches any drift between the two.

**The write-path boundary (read this before touching `app/api/routers/
blog.py`).** `sanitize_blog_html()` below is called by the blog router's
create/update handlers BEFORE `BlogPost.body_html` is ever persisted — a
post can NEVER reach the database with unsanitized HTML. `body_json` (the
raw ProseMirror document) is stored OPAQUE, never sanitized and never
rendered anywhere public — it exists solely so the (later, Stage 13d UI)
TipTap editor can reload a post for re-editing, in the authenticated admin
context only. **The render rule, stated plainly: only `body_html` is ever
rendered to an end user. `body_json` is never rendered — reloaded into the
editor only.** Any future public-facing blog render endpoint MUST render
`body_html` and MUST NOT render `body_json` (e.g. via a ProseMirror-to-HTML
renderer that bypasses this sanitizer) — doing so would reopen the exact
stored-XSS hole this module exists to close.

**The policy — NO v1 images, text formatting + links only** (the
user-confirmed Stage 13 scope decision: no `<img>` at all, keeping zero
image/SSRF surface in the sanitizer's allowlist):

- `ALLOWED_TAGS`: `p, br, h2, h3, h4, strong, em, u, s, blockquote, ul,
  ol, li, a, code, pre, hr`. Nothing else survives — nh3's allowlist model
  means every tag NOT in this set is dropped (its children are kept as
  plain text unless the tag is also in `CLEAN_CONTENT_TAGS`, below), never
  passed through unescaped. `script`/`style`/`iframe`/`object`/`embed`/
  `svg`/`math`/`form`/`img` are all absent, so all of them are stripped —
  `img` deliberately absent per the v1 "no images" decision above.
- `ALLOWED_ATTRIBUTES`: `{"a": {"href", "title"}}` only — NO global
  attributes (no `class`/`style`/`id`/`on*` on any tag, including `a`).
  This is what strips inline `style="expression(...)"` and every
  `onclick`/`onerror`/`onload` handler, on `a` or any other allowed tag.
- `ALLOWED_URL_SCHEMES`: `{"https", "http", "mailto"}` for `a[href]` —
  `javascript:`, `data:`, and `vbscript:` are all excluded, so nh3 drops
  the `href` attribute entirely for any of those (the link text survives,
  de-fanged, not the tag itself: see this module's own test coverage and
  `tests/test_blog.py`'s stored-XSS proof).
- `LINK_REL`: forced onto every surviving `<a>` regardless of what the
  input had (or didn't have) — `noopener noreferrer nofollow`. `noopener
  noreferrer` closes the classic `target="_blank"` tab-nabbing/referrer
  leak (moot here since `target` itself isn't in `ALLOWED_ATTRIBUTES`, but
  cheap and correct defense-in-depth); `nofollow` is an editorial policy
  (don't pass SEO authority through arbitrary admin-authored links) rather
  than a security control.
- `CLEAN_CONTENT_TAGS`: `{"script", "style"}` — these two are stripped
  ALONG WITH their text content (nh3's own documented default for this
  parameter; pinned here explicitly rather than left implicit, so this
  module's policy is fully self-contained and doesn't silently change
  behavior on an nh3 upgrade that alters its own default). Every other
  disallowed tag (`iframe`, `svg`, `object`, `img`, ...) is still stripped
  by `tags=ALLOWED_TAGS` alone — only script/style content specifically
  needs the stronger "drop the text too" treatment (a bare `<script>`
  removal would otherwise leave the JS source sitting in the page as
  visible text, not executable, but still noise no post should ever
  render).
- Comments are stripped (`strip_comments=True`) — an HTML comment is inert
  in every real browser, but stripping it is one less thing to reason
  about and matches nh3's own secure default.

Every constant below is `frozenset`/`dict[str, frozenset[str]]` — immutable
by convention (nothing in this module mutates them after import), so a
caller can't accidentally widen the policy by mutating a shared list in
place."""

from __future__ import annotations

import nh3

# --- THE policy (mirror byte-for-byte in core/services/sanitize.py) -------

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

# Forced onto every surviving <a>, replacing whatever rel (if any) the
# input had -- nh3's own `link_rel` option, not a post-processing step.
LINK_REL: str = "noopener noreferrer nofollow"

# Stripped ALONG WITH their text content -- see module docstring.
CLEAN_CONTENT_TAGS: frozenset[str] = frozenset({"script", "style"})


def sanitize_blog_html(raw_html: str) -> str:
    """THE write-path boundary function -- see module docstring. Pure and
    stateless (no I/O, no shared mutable state), safe to call as many
    times as needed (e.g. once on create, again on every update) without
    any setup/teardown. Idempotent in practice: re-sanitizing already-clean
    output produces the same output again (nh3's allowlist model has no
    "if already clean, skip" special case to need one)."""
    return nh3.clean(
        raw_html,
        tags=set(ALLOWED_TAGS),
        attributes={tag: set(attrs) for tag, attrs in ALLOWED_ATTRIBUTES.items()},
        url_schemes=set(ALLOWED_URL_SCHEMES),
        link_rel=LINK_REL,
        clean_content_tags=set(CLEAN_CONTENT_TAGS),
        strip_comments=True,
    )
