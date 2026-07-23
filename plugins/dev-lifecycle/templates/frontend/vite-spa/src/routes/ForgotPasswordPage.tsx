import type { ReactNode } from "react";
import { Link } from "react-router";
import { useMutation } from "@tanstack/react-query";
import { z } from "zod";
import { requestPasswordResetAuthRequestPasswordResetPost } from "@repo/api-client";
import { ApiError, applyEnvelopeToForm, unwrap, useZodForm } from "@repo/web-shared";
import { AuthCard } from "../components/AuthCard";
import { Banner, Button, TextInput } from "../components/form";

const schema = z.object({ email: z.email("Enter a valid email address") });
type Values = z.infer<typeof schema>;

/**
 * Request a password-reset link. The backend ALWAYS returns 202 with an empty
 * body whether or not the email has an account (anti-enumeration), so on
 * success we show the same generic confirmation either way — never "no such
 * account". A 422 (only reachable if client validation is bypassed) maps to the
 * field.
 */
export const ForgotPasswordPage = (): ReactNode => {
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useZodForm(schema, { defaultValues: { email: "" } });

  const mutation = useMutation({
    mutationFn: async (email: string) =>
      unwrap(await requestPasswordResetAuthRequestPasswordResetPost({ email })),
  });

  const onSubmit = handleSubmit(async (values: Values) => {
    try {
      await mutation.mutateAsync(values.email);
    } catch (err) {
      if (applyEnvelopeToForm(err, setError)) return;
      setError("root", {
        message: err instanceof ApiError ? err.message : "Something went wrong. Please try again.",
      });
    }
  });

  const backToSignIn = (
    <Link className="text-primary hover:underline" to="/login">
      Back to sign in
    </Link>
  );

  if (mutation.isSuccess) {
    return (
      <AuthCard title="Check your email" footer={backToSignIn}>
        <Banner tone="success">
          If an account exists for that email, we&apos;ve sent a link to reset your password.
        </Banner>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title="Reset your password"
      subtitle="Enter your email and we'll send a reset link."
      footer={backToSignIn}
    >
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        {errors.root?.message && <Banner tone="error">{errors.root.message}</Banner>}
        <TextInput
          label="Email"
          type="email"
          autoComplete="email"
          registration={register("email")}
          error={errors.email}
        />
        <Button type="submit" loading={isSubmitting}>
          Send reset link
        </Button>
      </form>
    </AuthCard>
  );
};
