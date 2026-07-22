import { afterEach, describe, expect, it, vi } from "vitest";
import { customFetch } from "./mutator";

describe("customFetch", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("resolves { data, status, headers } for a JSON response", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ status: "ok" }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await customFetch<{ data: { status: string }; status: number }>("/health");

    expect(result.status).toBe(200);
    expect(result.data).toEqual({ status: "ok" });
    expect(fetchMock).toHaveBeenCalledWith(
      "/health",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
  });

  it("resolves non-2xx responses instead of throwing, for documented error responses", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: [] }), {
          status: 422,
          headers: { "content-type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await customFetch<{ data: unknown; status: number }>("/items", {
      method: "POST",
    });

    expect(result.status).toBe(422);
    expect(result.data).toEqual({ detail: [] });
  });

  it("sets a default Content-Type without clobbering caller-supplied headers", async () => {
    // Typed against `typeof fetch` (rather than an arg-less arrow) so
    // `.mock.calls` infers the real [url, init] tuple below.
    const fetchMock = vi.fn<typeof fetch>(
      async () => new Response("plain text", { status: 200, headers: { "content-type": "text/plain" } }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await customFetch("/health", { headers: { Authorization: "Bearer token" } });

    const call = fetchMock.mock.calls[0];
    expect(call).toBeDefined();
    const [, options] = call!;
    const headers = new Headers(options?.headers);
    expect(headers.get("Authorization")).toBe("Bearer token");
    expect(headers.get("Content-Type")).toBe("application/json");
  });
});
