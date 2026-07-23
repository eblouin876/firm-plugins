import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { QueryClientProvider } from "@tanstack/react-query";
import { configureApiClient } from "@repo/api-client";
import type { FlagOut, PageFlagOut } from "@repo/api-client";
import { AuthProvider, createQueryClient, getAccessToken } from "@repo/web-shared";
import ModerationPage from "../../app/(app)/moderation/page";

// Integration test for the Stage 13c moderation queue — same
// MSW-at-the-network-boundary strategy as `users.test.tsx`/`blog.test.tsx`:
// real `@repo/api-client` generated hooks/functions, real react-query, MSW
// stubbing the merged 13c `/admin/flags*` endpoints. `next/navigation` is
// mocked defensively, matching this block's other tests, even though this
// page never calls `useRouter`/`useSearchParams`.

const ORIGIN = "http://localhost"; // jsdom's origin (see vitest.config.ts environmentOptions)

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterAll(() => server.close());

afterEach(() => {
  server.resetHandlers();
  configureApiClient({ baseUrl: "" });
});

beforeEach(() => {
  configureApiClient({ baseUrl: ORIGIN, cookieMode: true, getAccessToken });
});

const makeFlags = (): FlagOut[] => [
  {
    id: "flag-open-post",
    target_type: "blog_post",
    target_id: "post-1",
    reporter_id: "user-reporter",
    reason: "This post contains spam links.",
    status: "open",
    resolved_by_id: null,
    resolved_at: null,
    resolution_note: null,
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "flag-open-comment",
    target_type: "comment",
    target_id: "comment-1",
    reporter_id: null,
    reason: "Harassing comment.",
    status: "open",
    resolved_by_id: null,
    resolved_at: null,
    resolution_note: null,
    created_at: "2026-01-02T00:00:00Z",
  },
  {
    id: "flag-resolved-user",
    target_type: "user",
    target_id: "user-9",
    reporter_id: "user-reporter",
    reason: "Impersonation.",
    status: "resolved",
    resolved_by_id: "admin-1",
    resolved_at: "2026-01-03T00:00:00Z",
    resolution_note: "Banned the account.",
    created_at: "2026-01-02T12:00:00Z",
  },
];

const toPage = (items: FlagOut[]): PageFlagOut => ({
  items,
  total: items.length,
  page: 1,
  size: 20,
  pages: 1,
});

const renderPage = () =>
  render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <ModerationPage />
      </AuthProvider>
    </QueryClientProvider>,
  );

describe("Moderation queue page", () => {
  it("renders a page of flags from GET /admin/flags, defaulting to the open filter", async () => {
    let capturedUrl: URL | null = null;
    server.use(
      http.get(`${ORIGIN}/admin/flags`, ({ request }) => {
        capturedUrl = new URL(request.url);
        return HttpResponse.json(toPage(makeFlags()), { status: 200 });
      }),
    );

    renderPage();

    expect(await screen.findByText("This post contains spam links.")).toBeInTheDocument();
    expect(screen.getByText("Harassing comment.")).toBeInTheDocument();
    expect(screen.getByText("Impersonation.")).toBeInTheDocument();
    expect(screen.getByText("3 flags")).toBeInTheDocument();

    // The default status filter is "open" — reflected both in the select's
    // value and the actual `?status=open` request sent.
    expect(screen.getByLabelText("Status")).toHaveValue("open");
    await waitFor(() => expect(capturedUrl?.searchParams.get("status")).toBe("open"));

    // Only the two open flags get Resolve/Dismiss triggers; the resolved
    // one shows its read-only resolution instead.
    const openPostRow = screen.getByText("This post contains spam links.").closest("tr") as HTMLElement;
    expect(within(openPostRow).getByRole("button", { name: "Resolve" })).toBeInTheDocument();
    expect(within(openPostRow).getByRole("button", { name: "Dismiss" })).toBeInTheDocument();

    const resolvedRow = screen.getByText("Impersonation.").closest("tr") as HTMLElement;
    expect(within(resolvedRow).queryByRole("button", { name: "Resolve" })).not.toBeInTheDocument();
    expect(within(resolvedRow).getByText("Banned the account.")).toBeInTheDocument();
  });

  it("resolving a comment flag with ban_author calls POST .../resolve with the right body and refetches", async () => {
    let flags = makeFlags();
    let getCount = 0;
    let capturedBody: unknown = null;

    server.use(
      http.get(`${ORIGIN}/admin/flags`, () => {
        getCount += 1;
        return HttpResponse.json(toPage(flags), { status: 200 });
      }),
      http.post(`${ORIGIN}/admin/flags/:id/resolve`, async ({ request, params }) => {
        capturedBody = await request.json();
        flags = flags.map((flag) =>
          flag.id === params.id
            ? {
                ...flag,
                status: "resolved" as const,
                resolved_by_id: "admin-1",
                resolved_at: "2026-01-05T00:00:00Z",
                resolution_note: null,
              }
            : flag,
        );
        const updated = flags.find((flag) => flag.id === params.id);
        return HttpResponse.json(updated, { status: 200 });
      }),
    );

    const user = userEvent.setup();
    renderPage();

    const commentRow = (await screen.findByText("Harassing comment.")).closest("tr") as HTMLElement;
    await waitFor(() => expect(getCount).toBe(1));

    await user.click(within(commentRow).getByRole("button", { name: "Resolve" }));

    const dialog = await screen.findByRole("dialog");
    await user.selectOptions(within(dialog).getByLabelText("Action"), "ban_author");
    await user.click(within(dialog).getByRole("button", { name: "Resolve" }));

    await waitFor(() => expect(capturedBody).toEqual({ action: "ban_author" }));
    // Success invalidates the list query — a real second GET fires.
    await waitFor(() => expect(getCount).toBeGreaterThanOrEqual(2));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => {
      const refreshedRow = screen.getByText("Harassing comment.").closest("tr") as HTMLElement;
      // The Status column's badge — the row's Actions column no longer
      // offers Resolve/Dismiss once resolved, so this is the one place
      // "resolved" appears in the row.
      expect(within(refreshedRow).getByText("resolved")).toBeInTheDocument();
      expect(within(refreshedRow).queryByRole("button", { name: "Resolve" })).not.toBeInTheDocument();
    });
  });

  it("surfaces a 409 self-protection conflict from the server without crashing", async () => {
    const flags = makeFlags();
    let getCount = 0;

    server.use(
      http.get(`${ORIGIN}/admin/flags`, () => {
        getCount += 1;
        return HttpResponse.json(toPage(flags), { status: 200 });
      }),
      http.post(`${ORIGIN}/admin/flags/:id/resolve`, () =>
        HttpResponse.json(
          { error: { code: "conflict", message: "An admin cannot ban their own account." } },
          { status: 409 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderPage();

    const commentRow = (await screen.findByText("Harassing comment.")).closest("tr") as HTMLElement;
    await waitFor(() => expect(getCount).toBe(1));

    await user.click(within(commentRow).getByRole("button", { name: "Resolve" }));
    const dialog = await screen.findByRole("dialog");
    await user.selectOptions(within(dialog).getByLabelText("Action"), "ban_author");
    await user.click(within(dialog).getByRole("button", { name: "Resolve" }));

    // The server's own conflict message, verbatim — not a generic fallback,
    // and the app did not crash rendering it.
    expect(
      await within(dialog).findByText("An admin cannot ban their own account."),
    ).toBeInTheDocument();
    // Still open — a failed mutation leaves the dialog up rather than
    // silently closing on error.
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    // No successful mutation → no invalidation → no second GET.
    expect(getCount).toBe(1);
  });

  it("the resolve dialog's action selector offers all four actions for a blog_post target", async () => {
    server.use(
      http.get(`${ORIGIN}/admin/flags`, () => HttpResponse.json(toPage(makeFlags()), { status: 200 })),
    );

    const user = userEvent.setup();
    renderPage();

    const postRow = (await screen.findByText("This post contains spam links.")).closest("tr") as HTMLElement;
    await user.click(within(postRow).getByRole("button", { name: "Resolve" }));
    const dialog = await screen.findByRole("dialog");
    const select = within(dialog).getByLabelText("Action") as HTMLSelectElement;
    const optionValues = Array.from(select.options).map((option) => option.value);
    expect(optionValues).toEqual(["none", "hide_content", "delete_content", "ban_author"]);
  });

  it("the resolve dialog's action selector only offers none/ban_author for a user target — guiding the admin away from the 422 the backend would otherwise raise", async () => {
    const openUserFlag: FlagOut = {
      id: "flag-open-user",
      target_type: "user",
      target_id: "user-42",
      reporter_id: "user-reporter",
      reason: "Repeated abusive messages.",
      status: "open",
      resolved_by_id: null,
      resolved_at: null,
      resolution_note: null,
      created_at: "2026-01-04T00:00:00Z",
    };
    server.use(
      http.get(`${ORIGIN}/admin/flags`, () => HttpResponse.json(toPage([openUserFlag]), { status: 200 })),
    );

    const user = userEvent.setup();
    renderPage();

    const userRow = (await screen.findByText("Repeated abusive messages.")).closest("tr") as HTMLElement;
    await user.click(within(userRow).getByRole("button", { name: "Resolve" }));
    const dialog = await screen.findByRole("dialog");
    const select = within(dialog).getByLabelText("Action") as HTMLSelectElement;
    const optionValues = Array.from(select.options).map((option) => option.value);
    expect(optionValues).toEqual(["none", "ban_author"]);
  });
});
