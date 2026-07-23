import { createBrowserRouter, Navigate } from "react-router";
import { App } from "./App";
import { ProtectedRoute } from "./routes/ProtectedRoute";
import { AdminRoute } from "./routes/AdminRoute";
import { LoginPage } from "./routes/LoginPage";
import { RegisterPage } from "./routes/RegisterPage";
import { VerifyEmailPage } from "./routes/VerifyEmailPage";
import { ForgotPasswordPage } from "./routes/ForgotPasswordPage";
import { ResetPasswordPage } from "./routes/ResetPasswordPage";
import { DashboardPage } from "./routes/DashboardPage";
import { AdminPage } from "./routes/AdminPage";

/**
 * The SPA route table (react-router v7 library mode — `createBrowserRouter` +
 * `RouterProvider`, wired in main.tsx). Routing lives HERE in the app, never in
 * @repo/web-shared (which stays router-agnostic so it also imports into a
 * Next.js client component).
 *
 * Shape:
 * - Public auth routes (login/register/verify-email/forgot/reset) render on
 *   their own, no shell.
 * - The authenticated branch is a layout route whose element is
 *   `<ProtectedRoute><App/></ProtectedRoute>` — the ProtectedRoute gate wraps
 *   the whole shell, so an unauthenticated visit to `/` or `/admin` redirects
 *   to `/login`. `/admin` is additionally wrapped in `<AdminRoute>` (the
 *   `admin` role gate).
 * - Unknown paths fall back to `/` (which itself redirects to login when
 *   logged out).
 *
 * `router` is exported so main.tsx can pass it to `<RouterProvider>` AND drive
 * `router.navigate("/login")` from `AuthProvider`'s `onAuthExpired` (an
 * imperative redirect from outside the React render tree).
 */
export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/register", element: <RegisterPage /> },
  { path: "/verify-email", element: <VerifyEmailPage /> },
  { path: "/forgot-password", element: <ForgotPasswordPage /> },
  { path: "/reset-password", element: <ResetPasswordPage /> },
  {
    element: (
      <ProtectedRoute>
        <App />
      </ProtectedRoute>
    ),
    children: [
      { index: true, element: <DashboardPage /> },
      {
        path: "admin",
        element: (
          <AdminRoute>
            <AdminPage />
          </AdminRoute>
        ),
      },
    ],
  },
  { path: "*", element: <Navigate to="/" replace /> },
]);
