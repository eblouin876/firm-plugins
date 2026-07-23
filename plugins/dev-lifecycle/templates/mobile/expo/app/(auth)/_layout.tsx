/**
 * Public (unauthenticated) route group. The auth gate: an already-authenticated
 * user has no business on a login screen, so redirect them into the protected
 * area. Uses <Redirect> (declarative) + replace semantics so the auth screen
 * never lands on the back stack.
 */
import { Redirect, Stack } from "expo-router";

import { useAuth } from "../../src/auth/useAuth";

export default function AuthLayout() {
  const { status } = useAuth();

  if (status === "authenticated") {
    return <Redirect href="/" />;
  }

  return <Stack screenOptions={{ headerShown: false }} />;
}
