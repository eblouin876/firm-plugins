import { ErrorCode } from "@repo/api-client";
import type { ErrorEnvelope } from "@repo/api-client";

// Helpers over the backend's ONE error shape — the `ErrorEnvelope`
// (`{ error: { code, message, details? } }`) every non-2xx response carries
// (see @repo/api-client's generated `ErrorEnvelope`/`ErrorCode`). A client
// switches on the stable machine `code`, NEVER on the human `message`.

/**
 * Structural type guard: is `value` a well-formed `ErrorEnvelope`? Written
 * structurally (not `instanceof`) because it inspects orval's parsed JSON
 * `data`, which is a plain object. Safe on `unknown` — the mutator can resolve
 * a body outside the documented union (a proxy's 502 HTML, an empty body), and
 * this returns false for all of them.
 */
export const isErrorEnvelope = (value: unknown): value is ErrorEnvelope => {
  if (value == null || typeof value !== "object") return false;
  const error = (value as { error?: unknown }).error;
  return (
    error != null &&
    typeof error === "object" &&
    typeof (error as { code?: unknown }).code === "string" &&
    typeof (error as { message?: unknown }).message === "string"
  );
};

/** The machine-matchable `code` if `value` is an envelope, else `undefined`. */
export const getErrorCode = (value: unknown): ErrorCode | undefined =>
  isErrorEnvelope(value) ? value.error.code : undefined;

/**
 * Map an `ErrorCode` to a user-facing string. The `default` branch is
 * MANDATORY and load-bearing: an undocumented code, an undocumented 5xx
 * status the mutator resolved outside the typed union (see the api-client
 * README's "Response shape covers documented statuses only"), or `undefined`
 * (no envelope at all) must all resolve to a safe generic message rather than
 * crash on an unmapped code. Keep the specific branches aligned with
 * @repo/api-client's `ErrorCode` members; new members fall through to the
 * default until given their own copy.
 */
export const errorCodeToMessage = (code: ErrorCode | undefined): string => {
  switch (code) {
    case ErrorCode.unauthenticated:
      return "Your session has expired. Please sign in again.";
    case ErrorCode.permission_denied:
      return "You don't have permission to do that.";
    case ErrorCode.not_found:
      return "We couldn't find what you were looking for.";
    case ErrorCode.validation_failed:
      return "Some of the information provided isn't valid. Please check it and try again.";
    case ErrorCode.conflict:
      return "That conflicts with the current state. Please refresh and try again.";
    case ErrorCode.rate_limited:
      return "Too many requests. Please wait a moment and try again.";
    case ErrorCode.internal_error:
      return "Something went wrong on our end. Please try again.";
    default:
      return "Something went wrong. Please try again.";
  }
};
