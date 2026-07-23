import type { ReactNode } from "react";
import { Link } from "react-router";
import { useMutation } from "@tanstack/react-query";
import { z } from "zod";
import { registerAuthRegisterPost } from "@repo/api-client";
import { ApiError, applyEnvelopeToForm, unwrap, useZodForm } from "@repo/web-shared";
import { AuthCard } from "../components/AuthCard";
import { Banner, Button, TextInput } from "../components/form";

const schema = z
  .object({
    email: z.email("Enter a valid email address"),
    password: z.string().min(8, "Use at least 8 characters"),
    confirmPassword: z.string(),
  })
  .refine((v) => v.password === v.confirmPassword, {
    path: ["confirmPassword"],
    message: "Passwords don't match",
  });
type Values = z.infer<typeof schema>;

/**
 * Create an account. The mutation's `mutationFn` wraps the generated
 * `registerAuthRegisterPost` in `unwrap(...)`, so a non-2xx (409 email-taken,
 * 422 validation) THROWS an `ApiError` the handler surfaces — a 422 onto the
 * fields, anything else onto a form-level banner. On success the backend may
 * require email verification before login, so we tell the user to check their
 * inbox rather than auto-signing them in.
 */
export const RegisterPage = (): ReactNode => {
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useZodForm(schema, {
    defaultValues: { email: "", password: "", confirmPassword: "" },
  });

  const mutation = useMutation({
    mutationFn: async (input: { email: string; password: string }) =>
      unwrap(await registerAuthRegisterPost({ email: input.email, password: input.password })),
  });

  const onSubmit = handleSubmit(async (values: Values) => {
    try {
      await mutation.mutateAsync({ email: values.email, password: values.password });
    } catch (err) {
      if (applyEnvelopeToForm(err, setError)) return;
      setError("root", {
        message:
          err instanceof ApiError
            ? err.message
            : "Unable to create your account. Please try again.",
      });
    }
  });

  if (mutation.isSuccess) {
    return (
      <AuthCard
        title="Check your email"
        footer={
          <Link className="text-primary hover:underline" to="/login">
            Back to sign in
          </Link>
        }
      >
        <Banner tone="success">
          Your account was created. We&apos;ve sent a verification link to your email — open it to
          finish setting up, then sign in.
        </Banner>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title="Create your account"
      footer={
        <span>
          Already have an account?{" "}
          <Link className="text-primary hover:underline" to="/login">
            Sign in
          </Link>
        </span>
      }
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
        <TextInput
          label="Password"
          type="password"
          autoComplete="new-password"
          registration={register("password")}
          error={errors.password}
        />
        <TextInput
          label="Confirm password"
          type="password"
          autoComplete="new-password"
          registration={register("confirmPassword")}
          error={errors.confirmPassword}
        />
        <Button type="submit" loading={isSubmitting}>
          Create account
        </Button>
      </form>
    </AuthCard>
  );
};
