/**
 * Root layout = app entry. It runs before any screen and is the one place to:
 *   1. configure @repo/api-client (ONCE, in BEARER mode — cookieMode omitted;
 *      cookie mode is never enabled on native, per the auth wiring);
 *   2. mount the app-wide providers (SafeAreaProvider, React Query, AuthProvider);
 *   3. hold the top-level navigator, showing a splash while auth state resolves.
 *
 * The public/protected split is enforced in each route group's own _layout
 * (app/(auth)/_layout.tsx, app/(app)/_layout.tsx) with a <Redirect>, not here.
 */
import { configureApiClient } from "@repo/api-client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { ActivityIndicator, StyleSheet, View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { AuthProvider } from "../src/auth/AuthProvider";
import { useAuth } from "../src/auth/useAuth";

// Bearer mode: the mutator attaches whatever Authorization header the caller
// sets (the auth engine sets `Bearer <access>`) and touches no cookies. The
// base URL is inlined from EXPO_PUBLIC_API_BASE_URL at build time; unset → ""
// (same-origin relative URLs). See the api-client README's "Configuration".
configureApiClient({ baseUrl: process.env.EXPO_PUBLIC_API_BASE_URL ?? "" });

const queryClient = new QueryClient();

function RootNavigator() {
  const { status } = useAuth();

  // Reading the refresh token out of SecureStore on cold start is async — show
  // a splash rather than flashing a screen we might immediately redirect away.
  if (status === "loading") {
    return (
      <View style={styles.center}>
        <ActivityIndicator accessibilityLabel="Loading" />
      </View>
    );
  }

  return <Stack screenOptions={{ headerShown: false }} />;
}

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <StatusBar style="auto" />
          <RootNavigator />
        </AuthProvider>
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
});
