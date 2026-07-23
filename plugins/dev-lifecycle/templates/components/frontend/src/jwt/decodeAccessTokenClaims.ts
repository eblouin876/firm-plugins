export interface AccessTokenClaims {
  /** The subject (user id) claim, or null if absent/malformed. */
  sub: string | null;
  /** The roles claim as a string list; empty when absent or malformed. */
  roles: string[];
}

/**
 * Decode the `roles`/`sub` claims out of a JWT access token's MIDDLE segment.
 *
 * ⚠️ UX-ONLY, NO SIGNATURE CHECK. This base64url-decodes the payload without
 * verifying the token's signature — the SERVER already verified it when it
 * issued the token, and the server's 401/403 on every protected call is the
 * REAL authorization gate. Use these claims only to shape the UI (which nav to
 * show, whether to render an admin-only link, how to greet the user) — NEVER
 * to make a security decision. A tampered token still fails server-side; the
 * worst a forged `roles` claim buys an attacker here is seeing a menu item
 * whose underlying request the backend still 403s.
 *
 * Never throws: a null/empty/malformed token yields `{ sub: null, roles: [] }`.
 * Uses only `atob` + `TextDecoder` (available in browsers, jsdom, and Node
 * 18+), called inside the function — no bundler/DOM globals at module load.
 */
export const decodeAccessTokenClaims = (
  accessToken: string | null | undefined,
): AccessTokenClaims => {
  const empty: AccessTokenClaims = { sub: null, roles: [] };
  if (!accessToken) return empty;

  const segments = accessToken.split(".");
  const payloadSegment = segments[1];
  if (segments.length < 2 || !payloadSegment) return empty;

  try {
    const payload: unknown = JSON.parse(base64UrlDecode(payloadSegment));
    if (payload === null || typeof payload !== "object") return empty;
    const record = payload as Record<string, unknown>;
    const sub = typeof record.sub === "string" ? record.sub : null;
    const roles = Array.isArray(record.roles)
      ? record.roles.filter((role): role is string => typeof role === "string")
      : [];
    return { sub, roles };
  } catch {
    return empty;
  }
};

const base64UrlDecode = (input: string): string => {
  // base64url → base64, then pad to a multiple of 4 for `atob`.
  const padLength = Math.ceil(input.length / 4) * 4;
  const base64 = input.replace(/-/g, "+").replace(/_/g, "/").padEnd(padLength, "=");
  const binary = atob(base64);
  // Rebuild the UTF-8 bytes so multi-byte claim values survive the round trip.
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return new TextDecoder().decode(bytes);
};
