import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router";
import { z } from "zod";
import { ApiError, applyEnvelopeToForm, useAuth, useZodForm } from "@repo/web-shared";
import { AuthCard } from "../components/AuthCard";
import { Banner, Button, TextInput } from "../components/form";

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
 */
export const LoginPage = (): ReactNode => {
  const { login } = useAuth();
  const navigate = useNavigate();
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useZodForm(schema, { defaultValues: { email: "", password: "" } });

  const onSubmit = handleSubmit(async (values: Values) => {
    try {
      await login(values.email, values.password);
      void navigate("/", { replace: true });
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
    <AuthCard
      title="Sign in"
      subtitle="Welcome back."
      footer={
        <div className="flex flex-col gap-1">
          <span>
            No account?{" "}
            <Link className="text-primary hover:underline" to="/register">
              Create one
            </Link>
          </span>
          <Link className="text-primary hover:underline" to="/forgot-password">
            Forgot your password?
          </Link>
        </div>
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
};
