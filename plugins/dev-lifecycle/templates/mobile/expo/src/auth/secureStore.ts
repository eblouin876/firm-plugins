/**
 * The SecureStore seam: the ONLY place `expo-secure-store` is touched. It
 * implements the engine's `TokenStorage` interface, so the auth engine stays
 * framework-free and testable against a fake (see authEngine.test.ts).
 *
 * The refresh token — the long-lived credential — lives here, in the OS-backed
 * secret store (iOS Keychain / Android Keystore), NEVER in AsyncStorage and
 * NEVER in a cookie (see `references/mobile/react-native.md`, "Storage"). The
 * access token is short-lived and stays in memory only (in the engine).
 */
import * as SecureStore from "expo-secure-store";

import type { TokenStorage } from "./authEngine";

const REFRESH_TOKEN_KEY = "auth.refresh_token";

// Only readable while the device is unlocked, and marked device-only so the
// token is never synced to iCloud Keychain — a stronger default for a bearer
// credential than the library's default accessibility.
const OPTIONS: SecureStore.SecureStoreOptions = {
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};

export const refreshTokenStore: TokenStorage = {
  get() {
    return SecureStore.getItemAsync(REFRESH_TOKEN_KEY, OPTIONS);
  },
  set(token) {
    return SecureStore.setItemAsync(REFRESH_TOKEN_KEY, token, OPTIONS);
  },
  async clear() {
    await SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY, OPTIONS);
  },
};
