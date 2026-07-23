import type { ReactNode } from "react";
import { useEffect, useRef } from "react";
import { Link, useSearchParams } from "react-router";
import { useMutation } from "@tanstack/react-query";
import { verifyEmailAuthVerifyEmailPost } from "@repo/api-client";
import { ApiError, unwrap } from "@repo/web-shared";
import { AuthCard } from "../components/AuthCard";
import { Banner } from "../components/form";

/**
 * Consumes the single-use token from the emailed verification link
 * (`/verify-email?token=…`) and POSTs it once on mount. The `mutationFn` wraps
 * the generated call in `unwrap(...)`, so a 401 (unknown/expired/used token)
 * throws an `ApiError` and lands on the error branch. Both terminal branches
 * are rendered: verified → sign in; invalid/expired → request a fresh link via
 * password reset (which also verifies the email, per the backend contract).
 */
export const VerifyEmailPage = (): ReactNode => {
  const [params] = useSearchParams();
  const token = params.get("token");
  const firedFor = useRef<string | null>(null);

  const mutation = useMutation({
    mutationFn: async (t: string) => unwrap(await verifyEmailAuthVerifyEmailPost({ token: t })),
  });
  const { mutate } = mutation;

  useEffect(() => {
    // Fire exactly once per token (guards against StrictMode's dev double-run).
    if (token && firedFor.current !== token) {
      firedFor.current = token;
      mutate(token);
    }
  }, [token, mutate]);

  const backToSignIn = (
    <Link className="text-primary hover:underline" to="/login">
      Back to sign in
    </Link>
  );

  if (!token) {
    return (
      <AuthCard title="Verify your email" footer={backToSignIn}>
        <Banner tone="error">This verification link is invalid or incomplete.</Banner>
      </AuthCard>
    );
  }

  if (mutation.isSuccess) {
    return (
      <AuthCard title="Email verified" footer={backToSignIn}>
        <Banner tone="success">Your email is verified. You can sign in now.</Banner>
      </AuthCard>
    );
  }

  if (mutation.isError) {
    const invalid = mutation.error instanceof ApiError && mutation.error.status === 401;
    return (
      <AuthCard
        title="Verification failed"
        footer={
          <Link className="text-primary hover:underline" to="/forgot-password">
            Request a new link
          </Link>
        }
      >
        <Banner tone="error">
          {invalid
            ? "This verification link is invalid or has expired."
            : "We couldn't verify your email. Please try again."}
        </Banner>
      </AuthCard>
    );
  }

  return (
    <AuthCard title="Verifying your email">
      <Banner tone="info">Verifying…</Banner>
    </AuthCard>
  );
};
