<!-- fragment: block:mobile/expo -->

## Setup
The Expo mobile app lives at `apps/mobile/` (Expo-managed, Expo Router).

1. Install workspace deps from the repo root: `just install` (or `pnpm install`).
2. Set the backend origin the app talks to — `EXPO_PUBLIC_API_BASE_URL` — in
   `apps/mobile/.env` (copy from `.env.example`). On a physical device,
   `localhost` is the device itself; use your machine's LAN IP or a tunnel.
   This value is **inlined into the bundle at build time and is not a secret.**
3. Start the dev server: `pnpm --filter mobile start` (or `just dev`, which runs
   every app's dev script). Open it in Expo Go or a development build.
4. Auth is **bearer mode**: the app keeps the access token in memory and the
   refresh token in `expo-secure-store`. Log in against a running backend; the
   protected landing calls `/auth/me` and renders the principal + roles.

**Native builds** (`npx expo prebuild`, `npx expo run:ios`/`run:android`, EAS)
need a Mac/Android toolchain and are run on a dev machine — the CI checks stop
at the JS layer (typecheck / lint / vitest).

## Maintenance
Expo-SDK-governed packages (`expo`, `expo-router`, `expo-secure-store`,
`react-native`, `react-native-screens`, `react-native-safe-area-context`,
`react`) are upgraded **together** by bumping the Expo SDK and running
`npx expo install --fix` — never hand-bump one off the SDK. `typescript`,
`eslint`, `typescript-eslint`, `prettier`, and `vitest` follow the
compatibility matrix's kit-wide pins. Run `just typecheck lint test` before
committing mobile changes; the auth-engine vitest suite is the guard on the
token/refresh/rotation/logout logic.

## Secrets
| Secret | Used by | Where to get it |
| --- | --- | --- |
| `EXPO_PUBLIC_API_BASE_URL` | mobile/expo | The deployed backend's origin (dev: your machine's LAN IP + port). NOT secret — inlined into the app bundle at build time; never store a real secret in an `EXPO_PUBLIC_*` var. |
