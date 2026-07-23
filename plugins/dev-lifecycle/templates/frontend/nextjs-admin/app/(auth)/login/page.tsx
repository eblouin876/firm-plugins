"use client";

import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { z } from "zod";
import { ApiError, applyEnvelopeToForm, useAuth, useZodForm } from "@repo/web-shared";
import { AuthCard } from "../../../components/AuthCard";
import { Banner, Button, TextInput } from "../../../components/form";

const schema = z.object({
  email: z.email("Enter a valid email address"),
  password: z.string().min(1, "Password is required"),
});
type Values = z.infer<typeof schema>;

/**
 * Sign in via web-shared's `useAuth().login` — the ONE path that updates the
 * in-memory access token + loads the principal. It sends `X-Auth-Mode: cookie`
 * (cookie mode) and throws an `ApiError` on a non-200: a 422 maps to fields via
 * `applyEnvelopeToForm`, a 401 becomes a generic credentials message (never
 * "which field was wrong" — mirrors the backend's anti-enumeration 401).
 * Clone of the `web` app's `LoginPage`, minus the register/forgot-password
 * footer links: admins are seeded (by a backend admin script/migration, not
 * built here — that's a 13b/13c concern), not self-signup, so this app ships
 * no `/register`, `/verify-email`, `/forgot-password`, or `/reset-password`
 * routes at all. On success, redirects to `/dashboard` — which is itself
 * whole-app admin-gated (see `app/(app)/layout.tsx`), so a non-admin who
 * somehow authenticates still can't reach any admin content past that point.
 */
export default function LoginPage(): ReactNode {
  const { login } = useAuth();
  const router = useRouter();
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useZodForm(schema, { defaultValues: { email: "", password: "" } });

  const onSubmit = handleSubmit(async (values: Values) => {
    try {
      await login(values.email, values.password);
      router.replace("/dashboard");
    } catch (err) {
      if (applyEnvelopeToForm(err, setError)) return;
      if (err instanceof ApiError && err.status === 401) {
        setError("root", { message: "Incorrect email or password." });
        return;
      }
      setError("root", {
        message: err instanceof ApiError ? err.message : "Unable to sign in. Please try again.",
      });
    }
  });

  return (
    <AuthCard title="Sign in" subtitle="Admin access only.">
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
          autoComplete="current-password"
          registration={register("password")}
          error={errors.password}
        />
        <Button type="submit" loading={isSubmitting}>
          Sign in
        </Button>
      </form>
    </AuthCard>
  );
}
