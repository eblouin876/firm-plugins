/**
 * Protected route group. The auth gate: anything under (app) assumes an
 * authenticated user, so an unauthenticated (or still-resolving) visitor is
 * redirected to login. Authorization is a property of the route tree here, not
 * a scattered per-screen check.
 */
import { Redirect, Stack } from "expo-router";

import { useAuth } from "../../src/auth/useAuth";

export default function AppLayout() {
  const { status } = useAuth();

  if (status !== "authenticated") {
    return <Redirect href="/login" />;
  }

  return <Stack screenOptions={{ headerShown: false }} />;
}
