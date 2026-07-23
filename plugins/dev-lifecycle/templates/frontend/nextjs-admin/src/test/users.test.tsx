import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { setupServer } from "msw/node";
import { http, HttpResponse } from "msw";
import { QueryClientProvider } from "@tanstack/react-query";
import { configureApiClient } from "@repo/api-client";
import type { AdminUserOut, PageAdminUserOut } from "@repo/api-client";
import { AuthProvider, createQueryClient, getAccessToken } from "@repo/web-shared";
import UsersPage from "../../app/(app)/users/page";

// Integration test for the Stage 13b user-management screen — same
// MSW-at-the-network-boundary strategy as `login-e2e.test.tsx`: real
// `@repo/api-client` generated hooks/functions, real react-query, MSW
// stubbing `GET /admin/users` + one action (`POST .../suspend`). Renders
// `UsersPage` directly (not through `app/(app)/layout.tsx`'s gates — those
// are covered by `login-e2e.test.tsx` and `AdminGate`'s own unit coverage;
// this file is about the page's own list/search/action/error behavior).
// `next/navigation` is mocked defensively, matching this block's other
// tests, even though this page itself never calls `useRouter`/
// `useSearchParams`.

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

const makeUsers = (): AdminUserOut[] => [
  {
    id: "user-active",
    email: "active@example.com",
    roles: ["admin"],
    status: "active",
    email_verified: true,
    created_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "user-suspended",
    email: "suspended@example.com",
    roles: [],
    status: "suspended",
    email_verified: false,
    created_at: "2026-01-02T00:00:00Z",
  },
  {
    id: "user-banned",
    email: "banned@example.com",
    roles: ["editor"],
    status: "banned",
    email_verified: true,
    created_at: "2026-01-03T00:00:00Z",
  },
];

const toPage = (items: AdminUserOut[]): PageAdminUserOut => ({
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
        <UsersPage />
      </AuthProvider>
    </QueryClientProvider>,
  );

describe("Users admin page", () => {
  it("renders a page of users from GET /admin/users", async () => {
    const users = makeUsers();
    server.use(
      http.get(`${ORIGIN}/admin/users`, () => HttpResponse.json(toPage(users), { status: 200 })),
    );

    renderPage();

    expect(await screen.findByText("active@example.com")).toBeInTheDocument();
    expect(screen.getByText("suspended@example.com")).toBeInTheDocument();
    expect(screen.getByText("banned@example.com")).toBeInTheDocument();
    // Status badges (lowercase — the raw `UserStatus` values, not the
    // capitalized filter-dropdown option labels).
    expect(screen.getByText("active")).toBeInTheDocument();
    expect(screen.getByText("suspended")).toBeInTheDocument();
    expect(screen.getByText("banned")).toBeInTheDocument();
    expect(screen.getByText("3 users")).toBeInTheDocument();
  });

  it("suspending a user calls POST /admin/users/{id}/suspend and refetches the list", async () => {
    let users = makeUsers();
    let getCount = 0;
    let suspendedUserId: string | null = null;

    server.use(
      http.get(`${ORIGIN}/admin/users`, () => {
        getCount += 1;
        return HttpResponse.json(toPage(users), { status: 200 });
      }),
      http.post(`${ORIGIN}/admin/users/:id/suspend`, ({ params }) => {
        suspendedUserId = params.id as string;
        users = users.map((user) =>
          user.id === suspendedUserId ? { ...user, status: "suspended" as const } : user,
        );
        const updated = users.find((user) => user.id === suspendedUserId);
        return HttpResponse.json(updated, { status: 200 });
      }),
    );

    const user = userEvent.setup();
    renderPage();

    const activeRow = (await screen.findByText("active@example.com")).closest("tr");
    expect(activeRow).not.toBeNull();
    await waitFor(() => expect(getCount).toBe(1));

    // The row's compact "Suspend" trigger — distinct text from the dialog's
    // "Suspend user" confirm button below.
    await user.click(within(activeRow as HTMLElement).getByRole("button", { name: "Suspend" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/active@example\.com/)).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Suspend user" }));

    await waitFor(() => expect(suspendedUserId).toBe("user-active"));
    // Success invalidates the list query — a real second GET fires, and its
    // (server-side, mutated) response shows the row's new status, proving
    // this was an actual refetch and not merely closing the dialog.
    await waitFor(() => expect(getCount).toBeGreaterThanOrEqual(2));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    await waitFor(() => {
      const refreshedRow = screen.getByText("active@example.com").closest("tr") as HTMLElement;
      expect(within(refreshedRow).getByText("suspended")).toBeInTheDocument();
    });
  });

  it("surfaces a 409 conflict from the server without crashing, and does not refetch", async () => {
    const users = makeUsers();
    let getCount = 0;

    server.use(
      http.get(`${ORIGIN}/admin/users`, () => {
        getCount += 1;
        return HttpResponse.json(toPage(users), { status: 200 });
      }),
      http.post(`${ORIGIN}/admin/users/:id/suspend`, () =>
        HttpResponse.json(
          { error: { code: "conflict", message: "An admin cannot suspend their own account." } },
          { status: 409 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderPage();

    const activeRow = (await screen.findByText("active@example.com")).closest("tr");
    await waitFor(() => expect(getCount).toBe(1));

    await user.click(within(activeRow as HTMLElement).getByRole("button", { name: "Suspend" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Suspend user" }));

    // The server's own conflict message, verbatim — not a generic fallback,
    // and the app did not crash rendering it.
    expect(
      await within(dialog).findByText("An admin cannot suspend their own account."),
    ).toBeInTheDocument();
    // Still open — a failed mutation leaves the dialog up rather than
    // silently closing on error.
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    // No successful mutation → no invalidation → no second GET.
    expect(getCount).toBe(1);
  });
});
