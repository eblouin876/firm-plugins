import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { AuthProvider, createQueryClient } from "@repo/web-shared";
import { LoginPage } from "./LoginPage";

// A route-level component test: the login screen renders and its zod form
// surfaces field errors — no network, so no MSW. AuthProvider is still required
// (LoginPage calls `useAuth`), and it mounts cleanly without firing a request
// (the /auth/me query stays disabled until a token exists). MemoryRouter
// provides the router context the screen's <Link>s and `useNavigate` need.
const renderLogin = () =>
  render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <MemoryRouter initialEntries={["/login"]}>
          <LoginPage />
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  );

describe("LoginPage", () => {
  it("renders the sign-in form", () => {
    renderLogin();
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("shows zod validation errors on an empty submit (before any network call)", async () => {
    const user = userEvent.setup();
    renderLogin();

    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Enter a valid email address")).toBeInTheDocument();
    expect(screen.getByText("Password is required")).toBeInTheDocument();
  });
});
