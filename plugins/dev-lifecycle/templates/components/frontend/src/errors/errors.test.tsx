import { render, screen } from "@testing-library/react";
import type { ErrorEnvelope } from "@repo/api-client";
import { ApiError, isApiError } from "./ApiError";
import { unwrap } from "./unwrap";
import type { ApiResult } from "./unwrap";
import { errorCodeToMessage, getErrorCode, isErrorEnvelope } from "./errorEnvelope";
import { ApiErrorBoundary } from "./ApiErrorBoundary";

const envelope = (code: string, message = "boom", details?: unknown): ErrorEnvelope =>
  ({ error: { code, message, details } }) as ErrorEnvelope;

const result = <T,>(status: number, data: T): ApiResult<T> => ({
  status,
  data,
  headers: new Headers(),
});

describe("isErrorEnvelope", () => {
  it("accepts a well-formed envelope and rejects everything else", () => {
    expect(isErrorEnvelope(envelope("not_found"))).toBe(true);
    expect(isErrorEnvelope({ error: { code: "x" } })).toBe(false); // no message
    expect(isErrorEnvelope({ nope: true })).toBe(false);
    expect(isErrorEnvelope("<html>502</html>")).toBe(false);
    expect(isErrorEnvelope(null)).toBe(false);
  });
});

describe("getErrorCode / errorCodeToMessage", () => {
  it("reads the code and maps documented codes to user strings", () => {
    expect(getErrorCode(envelope("permission_denied"))).toBe("permission_denied");
    expect(errorCodeToMessage("permission_denied")).toMatch(/permission/i);
    expect(errorCodeToMessage("validation_failed")).toMatch(/valid/i);
  });

  it("has a mandatory default for undefined / undocumented codes", () => {
    expect(getErrorCode({ not: "an envelope" })).toBeUndefined();
    // undefined (no envelope) and an out-of-union code both hit the default.
    expect(errorCodeToMessage(undefined)).toMatch(/something went wrong/i);
    expect(errorCodeToMessage("teapot" as never)).toMatch(/something went wrong/i);
  });
});

describe("unwrap", () => {
  it("returns data on a 2xx", () => {
    expect(unwrap(result(200, { ok: true }))).toEqual({ ok: true });
  });

  it("throws an ApiError carrying the status and envelope on a non-2xx", () => {
    try {
      unwrap(result(401, envelope("unauthenticated")));
      throw new Error("expected unwrap to throw");
    } catch (error) {
      expect(isApiError(error)).toBe(true);
      const apiError = error as ApiError;
      expect(apiError.status).toBe(401);
      expect(apiError.code).toBe("unauthenticated");
      expect(apiError.envelope).toEqual(envelope("unauthenticated"));
    }
  });

  it("throws an ApiError with no envelope when the body wasn't one (e.g. a proxy 502)", () => {
    try {
      unwrap(result(502, "<html>Bad Gateway</html>"));
      throw new Error("expected unwrap to throw");
    } catch (error) {
      const apiError = error as ApiError;
      expect(isApiError(error)).toBe(true);
      expect(apiError.status).toBe(502);
      expect(apiError.code).toBeUndefined();
      expect(apiError.message).toMatch(/something went wrong/i);
    }
  });
});

describe("ApiErrorBoundary", () => {
  const Boom = ({ error }: { error: Error }): never => {
    throw error;
  };

  it("catches an ApiError thrown during render and shows the fallback", () => {
    // React logs the caught error to console.error; silence it for a clean run.
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    const thrown = new ApiError(403, {
      error: { code: "permission_denied", message: "nope" },
    } as ErrorEnvelope);

    render(
      <ApiErrorBoundary
        fallback={(error) => (
          <div role="alert">
            {isApiError(error) ? `api:${error.status}:${error.code}` : "unknown"}
          </div>
        )}
      >
        <Boom error={thrown} />
      </ApiErrorBoundary>,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("api:403:permission_denied");
    spy.mockRestore();
  });

  it("renders children when nothing throws", () => {
    render(
      <ApiErrorBoundary fallback={() => <div>fallback</div>}>
        <div data-testid="child">hello</div>
      </ApiErrorBoundary>,
    );
    expect(screen.getByTestId("child")).toHaveTextContent("hello");
  });
});
