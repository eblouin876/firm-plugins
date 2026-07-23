import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import HomePage from "./page";

// Proves the SSR-public/client-auth split this block's README and
// docs/fragment.md describe: the public landing page renders with NO
// AuthProvider / QueryClientProvider in the tree at all (unlike every screen
// under `(auth)`/`(app)`, which throw without one — see `useAuth`'s "must be
// used within an <AuthProvider>" guard). `HomePage` is a plain server
// component (no hooks, no "use client"), so Testing Library can render it
// directly with no provider wrapper — this test IS the proof: if it needed
// one, this file wouldn't compile/run without adding it.
describe("HomePage (public landing)", () => {
  it("renders without any auth/query provider", () => {
    render(<HomePage />);
    expect(screen.getByRole("heading", { name: "Web App" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
  });
});
