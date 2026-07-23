import type { ReactNode } from "react";
import { Link, useSearchParams } from "react-router";
import { useMutation } from "@tanstack/react-query";
import { z } from "zod";
import { resetPasswordAuthResetPasswordPost } from "@repo/api-client";
import { ApiError, applyEnvelopeToForm, unwrap, useZodForm } from "@repo/web-shared";
import { AuthCard } from "../components/AuthCard";
import { Banner, Button, TextInput } from "../components/form";

const schema = z
  .object({
    password: z.string().min(8, "Use at least 8 characters"),
    confirmPassword: z.string(),
  })
  .refine((v) => v.password === v.confirmPassword, {
    path: ["confirmPassword"],
    message: "Passwords don't match",
  });
type Values = z.infer<typeof schema>;

/**
 * Set a new password using the single-use token from the reset link
 * (`/reset-password?token=…`). The `mutationFn` wraps the generated call in
 * `unwrap(...)`: a 401 (unknown/expired/used token) throws and surfaces as a
 * form banner, a 422 maps to fields. On success the backend revokes every
 * session, so we route the user back to sign in with the new password.
 */
export const ResetPasswordPage = (): ReactNode => {
  const [params] = useSearchParams();
  const token = params.get("token");
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useZodForm(schema, { defaultValues: { password: "", confirmPassword: "" } });

  const mutation = useMutation({
    mutationFn: async (input: { token: string; newPassword: string }) =>
      unwrap(
        await resetPasswordAuthResetPasswordPost({
          token: input.token,
          new_password: input.newPassword,
        }),
      ),
  });

  const onSubmit = handleSubmit(async (values: Values) => {
    if (!token) return;
    try {
      await mutation.mutateAsync({ token, newPassword: values.password });
    } catch (err) {
      if (applyEnvelopeToForm(err, setError)) return;
      setError("root", {
        message:
          err instanceof ApiError && err.status === 401
            ? "This reset link is invalid or has expired. Request a new one."
            : err instanceof ApiError
              ? err.message
              : "Unable to reset your password. Please try again.",
      });
    }
  });

  const backToSignIn = (
    <Link className="text-primary hover:underline" to="/login">
      Back to sign in
    </Link>
  );

  if (!token) {
    return (
      <AuthCard
        title="Reset your password"
        footer={
          <Link className="text-primary hover:underline" to="/forgot-password">
            Request a new link
          </Link>
        }
      >
        <Banner tone="error">This reset link is invalid or incomplete.</Banner>
      </AuthCard>
    );
  }

  if (mutation.isSuccess) {
    return (
      <AuthCard title="Password updated" footer={backToSignIn}>
        <Banner tone="success">
          Your password has been reset. Sign in with your new password.
        </Banner>
      </AuthCard>
    );
  }

  return (
    <AuthCard title="Choose a new password" footer={backToSignIn}>
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        {errors.root?.message && <Banner tone="error">{errors.root.message}</Banner>}
        <TextInput
          label="New password"
          type="password"
          autoComplete="new-password"
          registration={register("password")}
          error={errors.password}
        />
        <TextInput
          label="Confirm new password"
          type="password"
          autoComplete="new-password"
          registration={register("confirmPassword")}
          error={errors.confirmPassword}
        />
        <Button type="submit" loading={isSubmitting}>
          Reset password
        </Button>
      </form>
    </AuthCard>
  );
};
