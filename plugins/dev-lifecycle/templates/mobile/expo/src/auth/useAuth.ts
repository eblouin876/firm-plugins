/**
 * The hook every screen uses to read auth state and drive login/logout. Throws
 * if used outside `<AuthProvider>` — a programming error worth failing loudly.
 */
import { useContext } from "react";

import { AuthContext, type AuthContextValue } from "./context";

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (value == null) {
    throw new Error("useAuth must be used inside <AuthProvider>");
  }
  return value;
}
