"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Activity } from "lucide-react";
import { request } from "@/lib/client-api";
import { Button } from "@/components/ui/primitives";
import { ErrorState } from "@/components/ui/feedback";
export default function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const router = useRouter();
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      await request(`/api/auth/${mode}`, "POST", {
        email: data.get("email"),
        password: data.get("password"),
      });
      router.push("/dashboard");
      router.refresh();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Unable to connect. Please retry.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth-page">
      <Link prefetch={false} href="/" className="brand">
        <Activity size={26} />
        JobPulse<span className="brand-dot">.</span>
      </Link>
      <section className="auth-panel">
        <h1>{mode === "login" ? "Welcome back" : "Create your account"}</h1>
        <p>
          {mode === "login"
            ? "Your next opportunity is waiting."
            : "A more focused way to find your next role."}
        </p>
        <form onSubmit={submit}>
          <label>
            Email
            <input
              name="email"
              type="email"
              autoComplete="email"
              required
              disabled={busy}
              placeholder="you@example.com"
            />
          </label>
          <div>
            <label htmlFor="password">Password</label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete={
                mode === "login" ? "current-password" : "new-password"
              }
              minLength={12}
              maxLength={128}
              required
              disabled={busy}
              aria-describedby="password-hint"
            />
            <span id="password-hint" className="field-hint">
              Use 12–128 characters.
            </span>
          </div>
          {error && <ErrorState message={error} />}
          <Button variant="primary" disabled={busy}>
            {busy ? "Please wait..." : mode === "login" ? "Log in" : "Sign up"}
          </Button>
        </form>
        <Link
          prefetch={false}
          className="auth-footer"
          href={mode === "login" ? "/signup" : "/login"}
        >
          {mode === "login"
            ? "Create an account"
            : "Already have an account? Log in"}
        </Link>
      </section>
      <p className="auth-note">
        Official careers. Personal matches. Your next move.
      </p>
    </main>
  );
}
