"use client";

import { forwardRef, useImperativeHandle } from "react";
import type { ReactNode } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import type { Editor, JSONContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Link from "@tiptap/extension-link";

// The Stage 13d TipTap WYSIWYG editor for blog post bodies. Pinned versions
// (@tiptap/react, @tiptap/pm, @tiptap/starter-kit, @tiptap/extension-link,
// all 3.28.0) come from references/compatibility-matrix.md's "Editor
// (WYSIWYG)" section — see this app's package.json.
//
// XSS boundary, stated plainly: the SERVER's `nh3` sanitizer
// (`app/services/sanitize.py`, run on every create/update) is the
// AUTHORITATIVE boundary for `body_html` — it's what actually gets persisted
// and, eventually, rendered to end users. Everything below (the `isSafeHref`
// checks, `rel`/protocol locking on the Link mark) is defense-in-depth on
// the ADMIN's OWN live editor session only: it stops an admin's own editor
// from ever constructing a `javascript:`/`data:` link in the first place, so
// there's one fewer place a malicious paste/autolink could matter — it does
// NOT replace, weaken, or substitute for the server-side sanitizer, and
// nothing rendered here is untrusted third-party content.
const SAFE_LINK_PROTOCOLS = ["http:", "https:", "mailto:", "tel:"];

/** Reject `javascript:`/`data:`/any other non-allowlisted scheme; a bare
 *  relative path or `#fragment` (no scheme at all) is allowed through. */
const isSafeHref = (href: string): boolean => {
  const trimmed = href.trim();
  if (trimmed.length === 0) return false;
  // No `scheme:` prefix at all => relative/fragment link, not a scheme-based
  // attack surface.
  if (!/^[a-z][a-z0-9+.-]*:/i.test(trimmed)) return true;
  try {
    return SAFE_LINK_PROTOCOLS.includes(new URL(trimmed).protocol);
  } catch {
    return false;
  }
};

export interface BlogEditorContent {
  /** `editor.getJSON()` — the opaque ProseMirror doc, the source of truth
   *  persisted as `body_json` and what a later edit reloads from (never
   *  `body_html` — see `getContent`'s docstring below). */
  body_json: Record<string, unknown>;
  /** `editor.getHTML()` — sent as `body_html`; the SERVER re-sanitizes this
   *  with `nh3` before it's ever persisted or rendered to a reader, so this
   *  is best-effort/advisory on the wire, not itself a trust boundary. */
  body_html: string;
}

export interface BlogEditorHandle {
  /** Pull the editor's current content on save — deliberately imperative
   *  (a ref, not a continuous `onChange`) so typing doesn't re-render the
   *  parent form on every keystroke; the parent calls this once, at submit
   *  time. Returns a safe empty doc if the editor hasn't mounted yet. */
  getContent: () => BlogEditorContent;
  /** Whether the document has no user-entered content — lets a caller warn
   *  on an empty-body submit without duplicating TipTap's own emptiness
   *  rules. */
  isEmpty: () => boolean;
}

export interface BlogEditorProps {
  /** Seeds the editor from the post's `body_json` (the opaque ProseMirror
   *  doc, the source of truth) — NEVER from `body_html`. `undefined` starts
   *  a blank, empty document (the "new post" case). */
  initialContent?: Record<string, unknown>;
  /** `false` renders the content read-only (not used yet, but keeps the
   *  component usable outside an editable form later without a rewrite). */
  editable?: boolean;
}

/**
 * The blog post body editor: TipTap `StarterKit` (headings restricted to
 * h2–h4, matching the server's sanitizer allowlist — see
 * `app/services/sanitize.py`) plus an explicitly-configured `Link` mark.
 * `immediatelyRender: false` is the TipTap v3 SSR guard — Next.js server-
 * renders this "use client" component's initial HTML too, and TipTap's
 * default (`immediatelyRender: true`) reads `window`/constructs a DOM
 * editor view during that very first render pass, which throws under SSR;
 * `false` defers the actual editor mount to a client-only effect, so
 * `useEditor` returns `null` until then (guarded in the render below) and
 * `next build` doesn't error.
 */
export const BlogEditor = forwardRef<BlogEditorHandle, BlogEditorProps>(function BlogEditor(
  { initialContent, editable = true }: BlogEditorProps,
  ref,
): ReactNode {
  const editor = useEditor({
    immediatelyRender: false,
    editable,
    extensions: [
      StarterKit.configure({
        heading: { levels: [2, 3, 4] },
        // StarterKit v3 bundles its own Link mark — disable it here so the
        // explicitly-configured `Link` instance below (which needs its own
        // `isAllowedUri`/`rel` options) is the only one registered; leaving
        // both in would double-register the `link` mark.
        link: false,
      }),
      Link.configure({
        autolink: true,
        openOnClick: false,
        linkOnPaste: true,
        protocols: ["http", "https", "mailto", "tel"],
        defaultProtocol: "https",
        HTMLAttributes: {
          rel: "noopener noreferrer nofollow",
          target: "_blank",
        },
        // Defense-in-depth (see this file's top-of-module docstring): reject
        // any href whose scheme isn't on the allowlist — `javascript:`/
        // `data:` in particular — before TipTap ever applies the mark, for
        // autolink/paste as well as the toolbar's own "Add link" prompt
        // below (which also calls `isSafeHref` before dispatching the
        // command, belt-and-suspenders).
        isAllowedUri: (url) => isSafeHref(url),
      }),
    ],
    content: initialContent as JSONContent | undefined,
  });

  useImperativeHandle(
    ref,
    () => ({
      getContent: () => ({
        body_json: (editor?.getJSON() ?? { type: "doc", content: [] }) as Record<string, unknown>,
        body_html: editor?.getHTML() ?? "<p></p>",
      }),
      isEmpty: () => editor?.isEmpty ?? true,
    }),
    [editor],
  );

  return (
    <div className="rounded-md border border-border bg-surface">
      {editor && <EditorToolbar editor={editor} />}
      <div className="min-h-[240px] px-3 py-2">
        {editor ? (
          <EditorContent
            editor={editor}
            className="prose prose-sm max-w-none text-text focus:outline-none [&_.tiptap]:min-h-[200px] [&_.tiptap]:outline-none"
          />
        ) : (
          <p className="text-sm text-muted">Loading editor…</p>
        )}
      </div>
    </div>
  );
});

interface ToolbarButtonProps {
  onClick: () => void;
  isActive?: boolean;
  disabled?: boolean;
  label: string;
  children: ReactNode;
}

const ToolbarButton = ({ onClick, isActive, disabled, label, children }: ToolbarButtonProps): ReactNode => (
  <button
    type="button"
    aria-label={label}
    aria-pressed={isActive ?? false}
    disabled={disabled}
    onClick={onClick}
    className={[
      "rounded px-2 py-1 text-xs font-medium outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:opacity-40",
      isActive ? "bg-primary text-primary-foreground" : "text-text hover:bg-bg",
    ].join(" ")}
  >
    {children}
  </button>
);

/** Small, fixed toolbar — one button per StarterKit/Link command this
 *  editor exposes; nothing dynamic/overflowing. */
const EditorToolbar = ({ editor }: { editor: Editor }): ReactNode => {
  const setLink = (): void => {
    const previousHref = (editor.getAttributes("link").href as string | undefined) ?? "";
    // A simple prompt is the smallest correct UI for "enter a URL"; this
    // admin tool has no existing modal primitive worth building just for
    // this one field.
    const href = window.prompt("Link URL", previousHref);
    if (href === null) return; // cancelled
    const trimmed = href.trim();
    if (trimmed.length === 0) {
      editor.chain().focus().extendMarkRange("link").unsetLink().run();
      return;
    }
    if (!isSafeHref(trimmed)) {
      window.alert("That link isn't allowed. Use an http(s), mailto, or tel URL.");
      return;
    }
    editor.chain().focus().extendMarkRange("link").setLink({ href: trimmed }).run();
  };

  return (
    <div className="flex flex-wrap items-center gap-1 border-b border-border px-2 py-1.5">
      <ToolbarButton
        label="Bold"
        isActive={editor.isActive("bold")}
        onClick={() => editor.chain().focus().toggleBold().run()}
      >
        <span className="font-bold">B</span>
      </ToolbarButton>
      <ToolbarButton
        label="Italic"
        isActive={editor.isActive("italic")}
        onClick={() => editor.chain().focus().toggleItalic().run()}
      >
        <span className="italic">I</span>
      </ToolbarButton>
      <ToolbarButton
        label="Strikethrough"
        isActive={editor.isActive("strike")}
        onClick={() => editor.chain().focus().toggleStrike().run()}
      >
        <span className="line-through">S</span>
      </ToolbarButton>
      <span className="mx-1 h-4 w-px bg-border" aria-hidden="true" />
      {[2, 3, 4].map((level) => (
        <ToolbarButton
          key={level}
          label={`Heading ${level}`}
          isActive={editor.isActive("heading", { level })}
          onClick={() => editor.chain().focus().toggleHeading({ level: level as 2 | 3 | 4 }).run()}
        >
          H{level}
        </ToolbarButton>
      ))}
      <span className="mx-1 h-4 w-px bg-border" aria-hidden="true" />
      <ToolbarButton
        label="Bullet list"
        isActive={editor.isActive("bulletList")}
        onClick={() => editor.chain().focus().toggleBulletList().run()}
      >
        • List
      </ToolbarButton>
      <ToolbarButton
        label="Numbered list"
        isActive={editor.isActive("orderedList")}
        onClick={() => editor.chain().focus().toggleOrderedList().run()}
      >
        1. List
      </ToolbarButton>
      <ToolbarButton
        label="Blockquote"
        isActive={editor.isActive("blockquote")}
        onClick={() => editor.chain().focus().toggleBlockquote().run()}
      >
        “ Quote
      </ToolbarButton>
      <ToolbarButton
        label="Inline code"
        isActive={editor.isActive("code")}
        onClick={() => editor.chain().focus().toggleCode().run()}
      >
        {"</>"}
      </ToolbarButton>
      <span className="mx-1 h-4 w-px bg-border" aria-hidden="true" />
      <ToolbarButton label="Add link" isActive={editor.isActive("link")} onClick={setLink}>
        Link
      </ToolbarButton>
      <ToolbarButton
        label="Remove link"
        disabled={!editor.isActive("link")}
        onClick={() => editor.chain().focus().unsetLink().run()}
      >
        Unlink
      </ToolbarButton>
    </div>
  );
};
