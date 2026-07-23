import type { FieldValues, Path, UseFormSetError } from "react-hook-form";
import { ErrorCode } from "@repo/api-client";
import type { ErrorEnvelope } from "@repo/api-client";
import { ApiError } from "../errors/ApiError";
import { isErrorEnvelope } from "../errors/errorEnvelope";

/**
 * Map a backend `422 validation_failed` envelope onto react-hook-form field
 * errors. Accepts an `ApiError` (as thrown by `unwrap`), a raw `ErrorEnvelope`,
 * or anything else (returns false).
 *
 * Each `details[]` entry with a `field` becomes a per-field `setError`; entries
 * without a field (cross-field rules) and an envelope with no usable details
 * fall back to a form-level `root` error. Returns true when it applied at least
 * one error, so a caller can branch: server-side validation → surfaced on the
 * form; anything else → a toast/banner.
 *
 * Only `validation_failed` is handled here — other codes (401/403/409/…) are
 * not form-field problems and should be surfaced elsewhere.
 */
export const applyEnvelopeToForm = <TFieldValues extends FieldValues>(
  source: unknown,
  setError: UseFormSetError<TFieldValues>,
): boolean => {
  const envelope = toEnvelope(source);
  if (!envelope || envelope.error.code !== ErrorCode.validation_failed) return false;

  const details = envelope.error.details ?? [];
  let applied = false;
  for (const detail of details) {
    // `detail.field` comes from the (server-supplied) response body. Reject
    // any prototype-polluting segment before using it as a react-hook-form
    // set-path — cheap defense-in-depth for this shared package, in case a
    // malicious/injected 422 carries a field like `__proto__` or
    // `a.constructor.prototype.x`.
    const rawField = detail.field ?? "";
    if (rawField.split(".").some((seg) => seg === "__proto__" || seg === "constructor" || seg === "prototype")) {
      continue;
    }
    const name = (rawField ? rawField : "root") as Path<TFieldValues>;
    setError(name, { type: "server", message: detail.message });
    applied = true;
  }

  if (!applied) {
    setError("root" as Path<TFieldValues>, { type: "server", message: envelope.error.message });
    applied = true;
  }
  return applied;
};

const toEnvelope = (source: unknown): ErrorEnvelope | null => {
  if (source instanceof ApiError) return source.envelope ?? null;
  if (isErrorEnvelope(source)) return source;
  return null;
};
