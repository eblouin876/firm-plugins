import type { ErrorCode, ErrorEnvelope } from "@repo/api-client";
import { errorCodeToMessage, getErrorCode } from "./errorEnvelope";

/**
 * A thrown API failure. This is what turns orval's fetch-mode "documented
 * non-2xx resolves as `{ data, status }` (it does NOT throw)" into a real
 * error react-query / an error boundary can react to — `unwrap()` constructs
 * and throws one for any non-2xx status. Carries the HTTP `status`, the
 * envelope's machine `code` (when the body was a well-formed `ErrorEnvelope`),
 * and the raw `envelope` for callers that need `details`.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: ErrorCode | undefined;
  readonly envelope: ErrorEnvelope | undefined;

  constructor(status: number, envelope?: ErrorEnvelope) {
    const code = getErrorCode(envelope);
    super(errorCodeToMessage(code));
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.envelope = envelope;
    // Restore the prototype chain so `instanceof ApiError` holds even when
    // compiled down to a target where Error subclassing otherwise breaks it.
    Object.setPrototypeOf(this, ApiError.prototype);
  }
}

/** Narrowing guard used by the QueryClient's error handling and app code. */
export const isApiError = (error: unknown): error is ApiError => error instanceof ApiError;
