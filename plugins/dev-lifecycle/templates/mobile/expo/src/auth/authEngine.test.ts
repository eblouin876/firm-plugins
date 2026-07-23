import { beforeEach, describe, expect, it, vi } from "vitest";

import { createAuthEngine, type TokenResult, type TokenStorage } from "./authEngine";

// --- helpers ----------------------------------------------------------------

/** Build a JWT-shaped token so the engine's payload decoder can read `roles`
 * and `exp`. Only the payload segment matters — the signature is ignored.
 * Uses `btoa` (a global in Node 16+ and Hermes, DOM-typed) rather than
 * `Buffer`, so the block's `types: []` typecheck stays node-types-free. */
function makeJwt(payload: Record<string, unknown>): string {
  const b64url = (obj: unknown) =>
    btoa(JSON.stringify(obj)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `${b64url({ alg: "HS256", typ: "JWT" })}.${b64url(payload)}.signature`;
}

const FAR_FUTURE = Math.floor(Date.now() / 1000) + 3600;
const ACCESS_1 = makeJwt({ sub: "u1", roles: ["admin"], exp: FAR_FUTURE });
const ACCESS_2 = makeJwt({ sub: "u1", roles: ["admin", "editor"], exp: FAR_FUTURE });

/** In-memory fake for the SecureStore seam. */
function makeStorage(initial: string | null = null) {
  let value = initial;
  return {
    get: vi.fn(async () => value),
    set: vi.fn(async (token: string) => {
      value = token;
    }),
    clear: vi.fn(async () => {
      value = null;
    }),
  } satisfies TokenStorage & {
    get: ReturnType<typeof vi.fn>;
    set: ReturnType<typeof vi.fn>;
    clear: ReturnType<typeof vi.fn>;
  };
}

/** Stubbed generated-client adapter. Each method is a vi mock so individual
 * tests can override with mockResolvedValue(Once). The returned shape satisfies
 * AuthApi structurally, so it plugs straight into the engine. */
function makeApi() {
  return {
    login: vi.fn<(email: string, password: string) => Promise<TokenResult>>(async () => ({
      status: 200,
      accessToken: ACCESS_1,
      refreshToken: "r1",
    })),
    refresh: vi.fn<(refreshToken: string) => Promise<TokenResult>>(async () => ({
      status: 200,
      accessToken: ACCESS_2,
      refreshToken: "r2",
    })),
    logout: vi.fn<(refreshToken: string) => Promise<void>>(async () => {}),
  };
}

// --- tests ------------------------------------------------------------------

describe("authEngine", () => {
  let storage: ReturnType<typeof makeStorage>;
  let api: ReturnType<typeof makeApi>;

  beforeEach(() => {
    storage = makeStorage();
    api = makeApi();
  });

  it("login stores the refresh token, keeps the access token in memory, and authenticates", async () => {
    const engine = createAuthEngine({ storage, api });

    await engine.login("a@b.com", "pw");

    expect(api.login).toHaveBeenCalledWith("a@b.com", "pw");
    // Refresh token persisted; access token never handed to storage.
    expect(storage.set).toHaveBeenCalledWith("r1");
    expect(storage.set).not.toHaveBeenCalledWith(ACCESS_1);
    expect(engine.getSnapshot().status).toBe("authenticated");
    // Roles come from the access token's `roles` claim.
    expect(engine.getSnapshot().roles).toEqual(["admin"]);
  });

  it("login rejection (non-200) throws and does not authenticate", async () => {
    api.login.mockResolvedValueOnce({ status: 401, accessToken: null, refreshToken: null });
    const engine = createAuthEngine({ storage, api });
    await engine.bootstrap(); // real app bootstraps before showing the login screen
    expect(engine.getSnapshot().status).toBe("unauthenticated");

    await expect(engine.login("a@b.com", "wrong")).rejects.toThrow();
    expect(engine.getSnapshot().status).toBe("unauthenticated");
    expect(storage.set).not.toHaveBeenCalled();
  });

  it("attaches Authorization: Bearer <access> to an authorized request", async () => {
    const engine = createAuthEngine({ storage, api });
    await engine.login("a@b.com", "pw");

    const seen: RequestInit[] = [];
    const res = await engine.authorizedRequest(async (init) => {
      seen.push(init);
      return { status: 200, data: "ok" };
    });

    expect(res.status).toBe(200);
    expect(new Headers(seen[0]!.headers).get("Authorization")).toBe(`Bearer ${ACCESS_1}`);
  });

  it("on a 401, refreshes exactly once and retries once with the NEW token", async () => {
    const engine = createAuthEngine({ storage, api });
    await engine.login("a@b.com", "pw");
    storage.set.mockClear();

    const seen: RequestInit[] = [];
    let attempts = 0;
    const res = await engine.authorizedRequest(async (init) => {
      seen.push(init);
      attempts += 1;
      return attempts === 1 ? { status: 401 } : { status: 200, data: "ok" };
    });

    expect(res.status).toBe(200);
    expect(attempts).toBe(2);
    expect(api.refresh).toHaveBeenCalledTimes(1);
    // Retry carries the rotated access token, not the stale one.
    expect(new Headers(seen[1]!.headers).get("Authorization")).toBe(`Bearer ${ACCESS_2}`);
    // Rotation: the new refresh token overwrote storage.
    expect(storage.set).toHaveBeenCalledWith("r2");
  });

  it("shares one refresh across concurrent 401s (single-flight guard)", async () => {
    const engine = createAuthEngine({ storage, api });
    await engine.login("a@b.com", "pw");

    const oneRequest = () => {
      let attempts = 0;
      return engine.authorizedRequest(async () => {
        attempts += 1;
        return attempts === 1 ? { status: 401 } : { status: 200, data: "ok" };
      });
    };

    const [a, b] = await Promise.all([oneRequest(), oneRequest()]);

    expect(a.status).toBe(200);
    expect(b.status).toBe(200);
    // Both 401'd concurrently but only ONE refresh fired.
    expect(api.refresh).toHaveBeenCalledTimes(1);
  });

  it("a refresh-401 is terminal: clears storage + memory and goes unauthenticated (reuse detection)", async () => {
    api.refresh.mockResolvedValue({ status: 401, accessToken: null, refreshToken: null });
    const engine = createAuthEngine({ storage, api });
    await engine.login("a@b.com", "pw");

    const res = await engine.authorizedRequest(async () => ({ status: 401 }));

    expect(res.status).toBe(401);
    expect(storage.clear).toHaveBeenCalled();
    expect(engine.getSnapshot().status).toBe("unauthenticated");
    expect(engine.getSnapshot().roles).toEqual([]);
  });

  it("logout best-effort revokes then unconditionally clears storage + memory", async () => {
    const engine = createAuthEngine({ storage, api });
    await engine.login("a@b.com", "pw");

    await engine.logout();

    expect(api.logout).toHaveBeenCalledWith("r1");
    expect(storage.clear).toHaveBeenCalled();
    expect(engine.getSnapshot().status).toBe("unauthenticated");
  });

  it("logout clears locally even if the backend revoke call throws (idempotent)", async () => {
    api.logout.mockRejectedValueOnce(new Error("network"));
    const engine = createAuthEngine({ storage, api });
    await engine.login("a@b.com", "pw");

    await expect(engine.logout()).resolves.toBeUndefined();
    expect(storage.clear).toHaveBeenCalled();
    expect(engine.getSnapshot().status).toBe("unauthenticated");
  });

  it("bootstrap with a stored refresh token refreshes into an authenticated session", async () => {
    storage = makeStorage("r0");
    const engine = createAuthEngine({ storage, api });

    await engine.bootstrap();

    expect(api.refresh).toHaveBeenCalledWith("r0");
    expect(engine.getSnapshot().status).toBe("authenticated");
    expect(storage.set).toHaveBeenCalledWith("r2");
  });

  it("bootstrap with no stored token settles on unauthenticated without calling refresh", async () => {
    const engine = createAuthEngine({ storage, api });

    await engine.bootstrap();

    expect(api.refresh).not.toHaveBeenCalled();
    expect(engine.getSnapshot().status).toBe("unauthenticated");
  });

  it("proactively refreshes a near-expiry access token", async () => {
    const nearExpiry = makeJwt({ roles: ["admin"], exp: Math.floor(Date.now() / 1000) + 10 });
    api.login.mockResolvedValueOnce({ status: 200, accessToken: nearExpiry, refreshToken: "r1" });
    const engine = createAuthEngine({ storage, api });
    await engine.login("a@b.com", "pw");

    await engine.maybeProactiveRefresh();

    expect(api.refresh).toHaveBeenCalledTimes(1);
  });

  it("does not proactively refresh a token with plenty of life left", async () => {
    const engine = createAuthEngine({ storage, api });
    await engine.login("a@b.com", "pw"); // exp is FAR_FUTURE

    await engine.maybeProactiveRefresh();

    expect(api.refresh).not.toHaveBeenCalled();
  });
});
