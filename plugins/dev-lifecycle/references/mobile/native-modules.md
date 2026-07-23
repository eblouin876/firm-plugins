<!--
library: expo-native-modules
versions-covered: "Expo SDK 57 managed workflow"
last-verified: 2026-07-23
provenance: manual
versions-pinned-to: references/compatibility-matrix.md
sources:
  - https://docs.expo.dev/workflow/overview/
  - https://docs.expo.dev/modules/config-plugins/
  - https://docs.expo.dev/develop/development-builds/introduction/
  - https://docs.expo.dev/bare/overview/
-->

# Native modules in the managed workflow

Granular guidance on the **native-module boundary** of an Expo-managed app — what you can add without touching native code, what needs a config plugin, and when a dependency forces you out of the managed workflow. Read this when a mobile task reaches for a capability beyond JS (secure storage, camera, notifications, a third-party native SDK). Subordinate to the project's existing conventions. Pairs with `expo.md`.

## Contents
- The managed-workflow boundary
- Three tiers of native dependency
- Config plugins
- Development builds vs Expo Go
- When you must go bare (and how to decide)
- Kit posture

## The managed-workflow boundary
In the managed workflow you write **only JS/TS**; the `android/`/`ios/` native projects are generated at build time (`expo prebuild` / EAS) from `app.json` + config plugins, and are **not committed**. The upside is upgradability and a reviewable (JS-only) diff. The constraint: any native capability must arrive either as an **Expo SDK module** or as a library that ships a **config plugin** — a library that needs hand-edited native project files does not fit managed without extra machinery.

## Three tiers of native dependency
1. **Expo SDK modules** (`expo-secure-store`, `expo-camera`, `expo-notifications`, `expo-image-picker`, …) — first-party, version-governed by the SDK. Add with **`npx expo install <pkg>`** so you get the SDK-57 version, never `pnpm add`. This is the default and covers most needs. This kit's only native module is **`expo-secure-store`** (refresh-token storage).
2. **Third-party libraries with a config plugin** — a community/native library that ships an Expo config plugin (declared in `app.json`'s `plugins`) so prebuild injects its native config. Works in managed, but it is native code: it can't run in the stock Expo Go client and needs a **development build** (below).
3. **Libraries with native code and no config plugin** — require hand-editing the native projects. These do **not** fit the managed workflow; using one means either writing a config plugin for it or dropping to bare (below).

## Config plugins
A **config plugin** is a function that mutates the native project during `expo prebuild` (adds a permission, an entitlement, an SDK key, a native dependency). It's how a native library stays compatible with managed flow: you list it under `plugins` in `app.json` and never touch `android/`/`ios/` yourself. `expo-router` itself ships as a plugin; `expo-secure-store` needs none (it's a pure SDK module). Prefer a library **with** a plugin over one without — the plugin is what keeps the app regenerable.

## Development builds vs Expo Go
- **Expo Go** — the prebuilt client from the app stores; runs your JS against the **stock** set of native modules only. Fast to start, but it **cannot** load any native module outside that set (tier-2/3, and even some SDK modules with extra native config).
- **Development build** — a custom dev client (`npx expo run:*` or `eas build --profile development`) compiled with *your* app's exact native modules. Required the moment you add any native dependency Expo Go doesn't bundle. It still has fast JS refresh — it just carries your native side.

In this sandbox neither can run (no simulator, no Apple/Google toolchain), so anything that requires a build is **documented-manual** — the template's hermetic checks stop at the JS layer (`tsc`/`eslint`/`vitest`).

## When you must go bare (and how to decide)
Go **bare** (commit and hand-maintain `android/`/`ios/`) only when a required native dependency has **no config plugin** and writing one isn't viable. It's a one-way-ish door: you take on maintaining two native trees and lose the clean SDK-upgrade path. Decision order: (1) is there an Expo SDK module? → use it; (2) does the library have a config plugin? → managed + dev build; (3) can you write a small config plugin? → do that; (4) only then, bare. Record the reason in the block/app docs — an undocumented bare exit is a trap for the next upgrade.

## Kit posture
The `templates/mobile/expo` block is deliberately **managed and native-module-light**: its single native dependency is `expo-secure-store`, plus `expo-router`'s required native peers (`react-native-screens`, `react-native-safe-area-context`), all Expo-SDK-governed. No committed native projects, no bare exit, no tier-3 dependency. That keeps the template upgradable with the SDK and its whole verifiable surface in JS — the auth-context logic is tested hermetically (vitest against a fake SecureStore + stubbed api-client); the native build is documented-manual.
