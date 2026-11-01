"use client";
import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api-client";
import { Brand } from "@/components/common/shell";
import { ErrorNotice } from "@/components/common/data";
import type { User } from "@/types/api";
type Mode =
  | "login"
  | "register"
  | "forgot-password"
  | "reset-password"
  | "verify-email";
export function AuthForm({ mode }: { mode: Mode }) {
  const [error, setError] = useState<Error>();
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState("");
  const [registrationRole, setRegistrationRole] = useState("AUTHOR");
  const router = useRouter();
  const titles = {
    login: "Welcome back.",
    register: "Your next chapter starts here.",
    "forgot-password": "Let’s get you back in.",
    "reset-password": "A fresh start.",
    "verify-email": "Verify your email.",
  };
  return (
    <div className="auth-page">
      <aside className="auth-story">
        <Brand />
        <div>
          <div className="eyebrow">IDEAS INTO IMPACT</div>
          <h1>Every meaningful publication begins with a single idea.</h1>
          <p>
            A thoughtful home for your research. A clear path from manuscript to
            publication.
          </p>
        </div>
        <small>Carefully reviewed. Confidently published.</small>
      </aside>
      <main id="main-content" className="auth-form">
        <h1>{titles[mode]}</h1>
        <p>
          {mode === "login"
            ? "Sign in to your publishing workspace."
            : mode === "register"
              ? "Create an author account or apply to become a reviewer. Reviewer accounts require admin approval."
              : "Follow the instructions sent to your email address."}
        </p>
        <ErrorNotice error={error} />
        {success ? (
          <div className="notice success" role="status">
            {success}
          </div>
        ) : (
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setError(undefined);
              setBusy(true);
              const fields = new FormData(e.currentTarget);
              const payload = Object.fromEntries(fields);
              try {
                await api(`/auth/${mode}`, {
                  method: "POST",
                  body: JSON.stringify(payload),
                });
                if (mode === "login") {
                  const user = await api<User>("/me");
                  router.push(
                    `/${(user.roles.includes("AUTHOR") ? "AUTHOR" : user.roles[0]).toLowerCase()}`,
                  );
                } else
                  setSuccess(
                    mode === "register"
                      ? payload.role === "REVIEWER"
                        ? "Reviewer application submitted for admin review. You will receive an email when an admin approves or rejects your application."
                        : "Account created. Check your email to verify your address before signing in."
                      : mode === "forgot-password"
                        ? "If that address has an account, a password reset link is on its way."
                        : mode === "verify-email"
                          ? "Email verified. You can sign in if your account has been approved."
                          : "Password updated. Sign in with your new password.",
                  );
              } catch (e) {
                setError(
                  e instanceof ApiError && e.code === "REVIEWER_APPROVAL_PENDING"
                    ? new Error("Your reviewer application is awaiting admin approval. You can sign in once it is approved.")
                    : e instanceof ApiError && e.code === "REVIEWER_APPLICATION_REJECTED"
                      ? new Error("Your reviewer application was rejected. Check your email for the decision and reason.")
                      : e instanceof ApiError && e.code === "EMAIL_VERIFICATION_REQUIRED"
                        ? new Error("Verify your email using the link sent to your address before signing in.")
                        : e as Error,
                );
              } finally {
                setBusy(false);
              }
            }}
          >
            {mode === "register" && (
              <label>
                Register as
                <select name="role" value={registrationRole} onChange={(e) => setRegistrationRole(e.target.value)}>
                  <option value="AUTHOR">Author</option>
                  <option value="REVIEWER">Reviewer (admin approval required)</option>
                </select>
              </label>
            )}
            {mode === "register" && (
              <label>
                Full name
                <input
                  name="display_name"
                  autoComplete="name"
                  required
                  maxLength={150}
                />
              </label>
            )}
            {["login", "register", "forgot-password"].includes(mode) && (
              <label>
                Email address
                <input
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  maxLength={254}
                  placeholder="you@institution.edu"
                />
              </label>
            )}
            {["reset-password", "verify-email"].includes(mode) && (
              <label>
                Token from your email
                <input
                  name="token"
                  required
                  autoComplete="off"
                  defaultValue={
                    typeof window !== "undefined"
                      ? new URLSearchParams(window.location.search).get(
                          "token",
                        ) || ""
                      : ""
                  }
                />
              </label>
            )}
            {["login", "register", "reset-password"].includes(mode) && (
              <label>
                Password
                <input
                  name={mode === "reset-password" ? "new_password" : "password"}
                  type="password"
                  autoComplete={
                    mode === "login" ? "current-password" : "new-password"
                  }
                  required
                  minLength={mode === "login" ? 1 : 12}
                  maxLength={128}
                />
                {mode !== "login" && <small>Use at least 12 characters.</small>}
              </label>
            )}
            {mode === "login" && (
              <Link
                href="/forgot-password"
                className="text-link"
                style={{ alignSelf: "flex-end" }}
              >
                Forgot password?
              </Link>
            )}
            <button disabled={busy} className="button">
              {busy
                ? "Please wait…"
                : mode === "login"
                  ? "Sign in →"
                  : mode === "register"
                    ? registrationRole === "REVIEWER" ? "Apply as reviewer →" : "Create author account →"
                    : mode === "forgot-password"
                      ? "Send reset instructions"
                      : "Confirm"}
            </button>
          </form>
        )}
        <p style={{ marginTop: 25 }}>
          {mode === "login" ? (
            <>
              New to Scriptora?{" "}
              <Link href="/register" className="text-link">
                Create an account
              </Link>
            </>
          ) : (
            <Link className="text-link" href="/login">
              Back to sign in →
            </Link>
          )}
        </p>
      </main>
    </div>
  );
}
