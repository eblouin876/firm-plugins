import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { QueryClientProvider } from "@tanstack/react-query";
import { configureApiClient } from "@repo/api-client";
import type { BlogPostOut, BlogPostSummaryOut, PageBlogPostSummaryOut } from "@repo/api-client";
import { AuthProvider, createQueryClient, getAccessToken } from "@repo/web-shared";
import BlogPage from "../../app/(app)/blog/page";
import NewBlogPostPage from "../../app/(app)/blog/new/page";

// Integration tests for the Stage 13d blog admin screens — same
// MSW-at-the-network-boundary strategy as `users.test.tsx`/`login-e2e.test.tsx`:
// real `@repo/api-client` generated hooks/functions, real react-query, MSW
// stubbing the merged 13d `/admin/blog/*` endpoints.

const ORIGIN = "http://localhost"; // jsdom's origin (see vitest.config.ts environmentOptions)

const pushSpy = vi.fn<(path: string) => void>(() => {});

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: pushSpy }),
  useSearchParams: () => new URLSearchParams(),
  useParams: () => ({ id: "post-1" }),
}));

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterAll(() => server.close());

afterEach(() => {
  server.resetHandlers();
  configureApiClient({ baseUrl: "" });
  pushSpy.mockClear();
});

beforeEach(() => {
  configureApiClient({ baseUrl: ORIGIN, cookieMode: true, getAccessToken });
});

const makePosts = (): BlogPostSummaryOut[] => [
  {
    id: "post-draft",
    title: "A draft post",
    slug: "a-draft-post",
    status: "draft",
    published_at: null,
    author_id: "admin-1",
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "post-live",
    title: "A published post",
    slug: "a-published-post",
    status: "published",
    published_at: "2026-01-02T00:00:00Z",
    author_id: "admin-1",
    created_at: "2026-01-02T00:00:00Z",
  },
];

const toPage = (items: BlogPostSummaryOut[]): PageBlogPostSummaryOut => ({
  items,
  total: items.length,
  page: 1,
  size: 20,
  pages: 1,
});

const renderList = () =>
  render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <BlogPage />
      </AuthProvider>
    </QueryClientProvider>,
  );

const renderNewPost = () =>
  render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <NewBlogPostPage />
      </AuthProvider>
    </QueryClientProvider>,
  );

describe("Blog admin list", () => {
  it("renders a page of posts from GET /admin/blog/posts", async () => {
    const posts = makePosts();
    server.use(
      http.get(`${ORIGIN}/admin/blog/posts`, () => HttpResponse.json(toPage(posts), { status: 200 })),
    );

    renderList();

    expect(await screen.findByText("A draft post")).toBeInTheDocument();
    expect(screen.getByText("A published post")).toBeInTheDocument();
    expect(screen.getByText("draft")).toBeInTheDocument();
    expect(screen.getByText("published")).toBeInTheDocument();
    expect(screen.getByText("2 posts")).toBeInTheDocument();
  });

  it("publishing a draft calls POST /admin/blog/posts/{id}/publish and refetches the list", async () => {
    let posts = makePosts();
    let getCount = 0;
    let publishedPostId: string | null = null;

    server.use(
      http.get(`${ORIGIN}/admin/blog/posts`, () => {
        getCount += 1;
        return HttpResponse.json(toPage(posts), { status: 200 });
      }),
      http.post(`${ORIGIN}/admin/blog/posts/:id/publish`, ({ params }) => {
        publishedPostId = params.id as string;
        posts = posts.map((post) =>
          post.id === publishedPostId
            ? { ...post, status: "published" as const, published_at: "2026-02-01T00:00:00Z" }
            : post,
        );
        const updated = posts.find((post) => post.id === publishedPostId);
        return HttpResponse.json(updated, { status: 200 });
      }),
    );

    const user = userEvent.setup();
    renderList();

    const draftRow = (await screen.findByText("A draft post")).closest("tr");
    expect(draftRow).not.toBeNull();
    await waitFor(() => expect(getCount).toBe(1));

    await user.click(within(draftRow as HTMLElement).getByRole("button", { name: "Publish" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/A draft post/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Publish post" }));

    await waitFor(() => expect(publishedPostId).toBe("post-draft"));
    // Success invalidates the list query — a real second GET fires, and its
    // (server-side, mutated) response shows the row's new status.
    await waitFor(() => expect(getCount).toBeGreaterThanOrEqual(2));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => {
      const refreshedRow = screen.getByText("A draft post").closest("tr") as HTMLElement;
      expect(within(refreshedRow).getByText("published")).toBeInTheDocument();
    });
  });

  it("surfaces a 409 conflict from a re-publish attempt without crashing, and does not refetch", async () => {
    const posts = makePosts();
    let getCount = 0;

    server.use(
      http.get(`${ORIGIN}/admin/blog/posts`, () => {
        getCount += 1;
        return HttpResponse.json(toPage(posts), { status: 200 });
      }),
      http.post(`${ORIGIN}/admin/blog/posts/:id/unpublish`, () =>
        HttpResponse.json(
          { error: { code: "conflict", message: "Cannot unpublish a post that is not published." } },
          { status: 409 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderList();

    const liveRow = (await screen.findByText("A published post")).closest("tr");
    await waitFor(() => expect(getCount).toBe(1));

    await user.click(within(liveRow as HTMLElement).getByRole("button", { name: "Unpublish" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Unpublish post" }));

    // The stub's own conflict message renders verbatim without crashing.
    expect(
      await within(dialog).findByText("Cannot unpublish a post that is not published."),
    ).toBeInTheDocument();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(getCount).toBe(1);
  });
});

describe("New blog post", () => {
  it("submits both body_json (a ProseMirror doc) and body_html (a string), then redirects to the edit page", async () => {
    let capturedBody: { title: string; slug?: string; body_json: unknown; body_html: unknown } | null = null;

    server.use(
      http.post(`${ORIGIN}/admin/blog/posts`, async ({ request }) => {
        capturedBody = (await request.json()) as typeof capturedBody;
        const created: BlogPostOut = {
          id: "new-post-1",
          title: capturedBody!.title,
          slug: capturedBody!.slug ?? "new-post-1",
          status: "draft",
          published_at: null,
          author_id: "admin-1",
          created_at: "2026-03-01T00:00:00Z",
          body_json: capturedBody!.body_json as Record<string, unknown>,
          body_html: capturedBody!.body_html as string,
        };
        return HttpResponse.json(created, { status: 201 });
      }),
      http.get(`${ORIGIN}/admin/blog/posts`, () => HttpResponse.json(toPage([]), { status: 200 })),
    );

    const user = userEvent.setup();
    renderNewPost();

    // Wait for the TipTap editor to actually mount (immediatelyRender:false
    // defers it past the first render) before submitting — proves the real
    // editor, not just BlogEditor's null-safe fallback, is what supplies the
    // submitted content.
    await screen.findByRole("button", { name: "Bold" });

    await user.type(screen.getByLabelText("Title"), "My new post");
    await user.click(screen.getByRole("button", { name: "Create post" }));

    await waitFor(() => expect(capturedBody).not.toBeNull());
    const body = capturedBody as unknown as {
      title: string;
      body_json: { type?: string };
      body_html: string;
    };
    expect(body.title).toBe("My new post");
    // body_json: a ProseMirror doc object (has a "type": "doc" root, per
    // TipTap's own `editor.getJSON()` shape).
    expect(body.body_json).toBeTypeOf("object");
    expect(body.body_json.type).toBe("doc");
    // body_html: a string (TipTap's `editor.getHTML()`).
    expect(body.body_html).toBeTypeOf("string");

    await waitFor(() => expect(pushSpy).toHaveBeenCalledWith("/blog/new-post-1/edit"));
  });

  it("surfaces a 409 duplicate-slug conflict from the server without crashing", async () => {
    server.use(
      http.post(`${ORIGIN}/admin/blog/posts`, () =>
        HttpResponse.json(
          { error: { code: "conflict", message: "A post with this slug already exists." } },
          { status: 409 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderNewPost();

    await screen.findByRole("button", { name: "Bold" });
    await user.type(screen.getByLabelText("Title"), "Duplicate slug post");
    await user.click(screen.getByRole("button", { name: "Create post" }));

    expect(
      await screen.findByText("A post with this slug already exists."),
    ).toBeInTheDocument();
    expect(pushSpy).not.toHaveBeenCalled();
  });
});
