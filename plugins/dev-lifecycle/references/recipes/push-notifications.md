<!--
recipe: push-notifications
applies-to:
  - mobile block: templates/mobile/expo (the Expo push token + expo-notifications wiring)
  - backend block: fastapi OR django (the device-token registration endpoint + the Expo push service call — NEW, not yet in the kit; see "What the kit does not provide")
last-verified: 2026-07-23
provenance: manual
sources:
  - https://docs.expo.dev/push-notifications/overview/
  - https://docs.expo.dev/push-notifications/sending-notifications/
  - https://docs.expo.dev/versions/latest/sdk/notifications/
  - references/mobile/native-modules.md
  - templates/mobile/expo/README.md
  - references/security/secure-baseline.md
-->

# Push notifications (Expo)

Wire mobile push notifications end to end: the Expo app requests permission and obtains an Expo push token via `expo-notifications`, registers that token against the authenticated user on the backend, and the backend sends notifications through Expo's push service. **This recipe describes ADDING a capability the kit does not ship today** — there is no device-token model, no registration endpoint, and no push-sending code in `templates/mobile/expo` or any backend block as of this recipe's `last-verified` date (confirmed by inspection — grep both before trusting this claim to have not gone stale). Everything here is **subordinate to the project's existing conventions** — when they conflict, the project wins.

## Contents
- What this wires
- What the kit does not provide (read this first)
- Prerequisites
- Wire-up steps (mobile: obtain and register the token)
- Wire-up steps (backend: the device-token endpoint + sending)
- Security posture
- Doc fragment

## What this wires
Applying this recipe gives a project working push delivery to its Expo app: the app asks for notification permission, obtains an Expo push token (`ExponentPushToken[...]`) scoped to that device/install, sends it to an authenticated backend endpoint that upserts it against the calling user, and a backend-triggered send posts to Expo's push API, which fans the message out to APNs/FCM on the app's behalf — the project's own backend never talks to Apple's or Google's push services directly.

It **composes what already exists** and is explicit about what it adds:
- **`templates/mobile/expo`** — the existing Expo block this recipe extends: its `AuthProvider`/`authApi.ts` pattern (a thin generated-client adapter feeding a framework-free engine) is the shape a new `pushApi.ts`/token-registration call follows, and its bearer-mode `@repo/api-client` is the transport the registration call reuses — no new HTTP client.
- **`references/mobile/native-modules.md`** — names `expo-notifications` explicitly as one of the "Expo SDK modules... first-party, version-governed by the SDK" (its "Three tiers of native dependency" section, tier 1) and states the install convention (`npx expo install expo-notifications`, never `pnpm add`, so the SDK-57-compatible version resolves). This is the kit's only existing mention of push notifications anywhere — a name-check in a tiers list, not a wired component. This recipe is what actually wires it.
- **The existing auth component** (`templates/components/security/auth/`) — the device-token registration endpoint is an authenticated route like any other, gated the same way (`Depends(get_current_principal)` on FastAPI, the equivalent on Django) — no new auth mechanism.
- **The `background-jobs` recipe** — sending to Expo's push API is a network call that should not block the request that triggers it (an order shipped, a comment reply) — dispatch it through the same Celery task (Django) or `BackgroundTasks`/task-queue path (FastAPI) that recipe already wires, rather than awaiting it inline in a request handler.

## What the kit does not provide (read this first)
None of the following exist in this kit as of this recipe's `last-verified` date — this recipe's wire-up steps below are instructions for **adding** each of them, not for wiring an existing component:
- **No `expo-notifications` dependency** in `templates/mobile/expo/package.json` — only `expo-constants`, `expo-linking`, `expo-router`, `expo-secure-store`, `expo-status-bar` are installed today.
- **No device-token model, migration, or registration endpoint** in either `templates/backend/fastapi` or `templates/backend/django` — no `DeviceToken`/`PushToken` table, no `/devices`/`/push/register` route.
- **No Expo push-sending code** — no `expo-server-sdk` (Python) dependency, no call to `https://exp.host/--/api/v2/push/send` anywhere in either backend block.
- **No compatibility-matrix row** for `expo-notifications` or `expo-server-sdk` — pin both against their current PyPI/npm releases at implementation time (per the SDK-57-governed convention `native-modules.md` already documents for `expo-notifications`; `expo-server-sdk` has no SDK-version coupling, since it's a plain server-side HTTP client).
- **No push-specific transport exists yet**, though `references/wiring/mobile-backend.md` is the canonical Expo↔backend wiring contract (SecureStore/bearer auth, deep links) and flags push as a forward-looking tie to this recipe — treat that ref as the authoritative mobile/backend contract and this recipe's mobile/backend split below as subordinate to it.

Don't cite any of the above as already wired. A build agent applying this recipe is doing net-new work on both the mobile app and the backend, not composing a pre-built push component.

## Prerequisites
- The `end-to-end-auth` recipe (or equivalent) already wired — token registration must be behind auth; an anonymous device token has no user to notify.
- An Expo project ID / EAS project configured (`app.json`'s `extra.eas.projectId`) — required by `expo-notifications`' `getExpoPushTokenAsync` to mint a token scoped to the right project.
- iOS: an Apple Developer account with push capability enabled on the app's provisioning profile; Android: an FCM project linked via `google-services.json` — both are Expo/EAS build-configuration steps, not code changes, and (per `references/mobile/native-modules.md`'s "In this sandbox" note) can only be verified against a real development build, not in a hermetic JS-only test environment.
- A development build (not Expo Go) once `expo-notifications` is added — it's an Expo SDK module, but remote push specifically needs native config (APNs/FCM credentials) that a stock Expo Go client doesn't carry for a project's own app identity; per `native-modules.md`'s "Development builds vs Expo Go."

## Wire-up steps (mobile: obtain and register the token)
1. **Add the dependency the SDK-governed way**: `npx expo install expo-notifications` (never `pnpm add`) — per `native-modules.md`'s tier-1 convention, this resolves the SDK-57-compatible version rather than an arbitrary latest.
2. **Request permission and obtain the token**, only for an authenticated user (gate this behind the existing `AuthProvider`'s signed-in state — no point minting/registering a token for a logged-out session):
   ```typescript
   import * as Notifications from "expo-notifications";
   import Constants from "expo-constants";

   async function registerForPushNotifications(): Promise<string | null> {
     const { status: existing } = await Notifications.getPermissionsAsync();
     let status = existing;
     if (status !== "granted") {
       ({ status } = await Notifications.requestPermissionsAsync());
     }
     if (status !== "granted") return null;   // user declined — don't nag; respect the choice
     const projectId = Constants.expoConfig?.extra?.eas?.projectId;
     const { data: token } = await Notifications.getExpoPushTokenAsync({ projectId });
     return token;   // "ExponentPushToken[...]"
   }
   ```
3. **Register the token with the backend the same way `authApi.ts` adapts the generated client** — add a `pushApi.ts` following that file's exact shape (a thin adapter over `@repo/api-client`'s generated `registerDeviceTokenPushDevicesPost`-style operation once the backend endpoint from the next section exists and the client is regenerated), called once after login and again whenever `getExpoPushTokenAsync` returns a token that differs from the last one registered (a token can change — e.g. after an app reinstall).
4. **Deregister on logout.** Call the backend's delete/deactivate endpoint for the current device's token when the user signs out — a token left registered against a now-logged-out session risks notifying the wrong context if a different user later signs into the same device.

## Wire-up steps (backend: the device-token endpoint + sending)
1. **Add a `DeviceToken` model** — `user_id` (FK), `expo_push_token` (string, unique per token), `platform` (optional), timestamps — built on the same `db-mixins`/`repository` catalog components every other model in the kit already uses. One user can have several tokens (multiple devices); a token should be unique across the table (re-registering the same token, e.g. on re-login, upserts rather than duplicates).
2. **Add an authenticated registration endpoint** (`POST /push/devices` or similar), gated by `Depends(get_current_principal)` (FastAPI) / the equivalent on Django — exactly the auth component's existing dependency, no new auth mechanism. The endpoint upserts `(user_id, expo_push_token)`. Add a matching delete/deactivate endpoint for logout (see mobile step 4).
3. **Validate the token shape before storing it** — an Expo push token has a known format (`ExponentPushToken[...]` or a UUID-based `ExpoPushToken[...]` variant); reject anything that doesn't match rather than storing arbitrary client-supplied strings that will later be sent, unchecked, to Expo's API.
4. **Send via Expo's push API, dispatched through the background-jobs recipe's task path — never inline in the triggering request.** Add `expo-server-sdk` (Python) as a new dependency (or call Expo's REST endpoint directly with `httpx`/`requests` if the project prefers no extra dependency — the API is a plain authenticated-by-nothing-but-your-own-tokens JSON POST):
   ```python
   # Dispatched via Celery (.delay()) on the Django track, or the FastAPI
   # track's task-queue path per the background-jobs recipe — not awaited
   # inline in the request that triggers the notification.
   from exponent_server_sdk import PushClient, PushMessage

   def send_push(user_id: str, title: str, body: str, data: dict | None = None) -> None:
       tokens = get_active_tokens_for_user(user_id)   # from the DeviceToken table
       for token in tokens:
           try:
               PushClient().publish(PushMessage(to=token, title=title, body=body, data=data or {}))
           except Exception:
               logger.warning("push delivery failed", extra={"user_id": user_id})
               # a delivery failure here is logged, never raised into the caller —
               # same fire-and-forget, non-raising posture the transactional-email
               # recipe's EmailSender contract already establishes for this kit
   ```
5. **Handle Expo's delivery-receipt/ticket errors, in particular `DeviceNotRegistered`.** Expo's push API returns a receipt per token; a `DeviceNotRegistered` error means the token is permanently invalid (app uninstalled, OS-level unregister) — deactivate or delete that `DeviceToken` row so future sends stop retrying a dead token. Don't treat every non-`ok` receipt as a transient failure worth retrying indefinitely.
6. **Batch sends** when notifying many users at once (a broadcast) — Expo's API accepts up to 100 messages per request; batching is both an Expo-imposed limit and the efficient path, not just an optimization.

## Security posture
- **The device-token registration endpoint is authenticated** — never accept a token registration from an unauthenticated request; an attacker could otherwise register their own token against another user's session context if any other check were missing (defense-in-depth: the endpoint should also confirm the token is being registered by the same principal it's stored against, never a caller-supplied `user_id` in the request body).
- **A push token is not a secret, but it is user-identifying** — treat the `DeviceToken` table with the same access-control discipline as any other per-user PII-adjacent table (per `references/security/data-protection.md`): a user's own tokens are visible to that user and to system processes sending on their behalf, never to another user via an under-scoped admin/debug endpoint.
- **Never put sensitive content in a push notification's body** — a push notification typically renders on a lock screen; treat its `title`/`body` the same way a project would treat anything shown before authentication succeeds (no PII, no content the user hasn't already consented to seeing pre-auth).
- **Sending never blocks or raises into the triggering request** — per the background-jobs recipe's fire-and-forget discipline; a push-delivery failure must never fail the request/action that triggered the notification.

## Doc fragment
The portable fragment this recipe contributes to the project's root README when applied:

```markdown
### Push notifications (Expo)
- **Setup:** The mobile app requests permission and obtains an Expo push token (`expo-notifications`, added via `npx expo install`), registered against the authenticated user via a new `POST /push/devices` endpoint and deregistered on logout. The backend sends via Expo's push API (`expo-server-sdk`), dispatched through the background-jobs task path — never inline in the request that triggers a notification. `DeviceNotRegistered` receipts deactivate the stale token.
- **Secrets:** none new for Expo's push service itself (no API key — tokens are the credential). APNs/FCM credentials are configured at the EAS/build-credential level, not as an app secret.
- **Maintenance:** This is a kit addition, not a pre-built component — the `DeviceToken` model, both endpoints, and the send path are project code following this recipe's shape. Prune tokens on `DeviceNotRegistered`; batch broadcast sends (Expo's 100-message-per-request limit).
```

---
<!--
Recipe authored via the `recipe-author` skill (Stage 11, #34, batch 2). This
recipe is explicit that the kit ships NO push code today — no device-token
model, no registration endpoint, no send path, and expo-notifications is not
installed in templates/mobile/expo/package.json. Its only real anchor in the
existing kit is references/mobile/native-modules.md's tier-1 name-check of
expo-notifications and the templates/mobile/expo block's existing authApi.ts
adapter shape, both cited directly rather than a fabricated push component.
Composes the existing auth component (registration endpoint auth) and the
background-jobs recipe (non-blocking send dispatch) for everything else.
-->
