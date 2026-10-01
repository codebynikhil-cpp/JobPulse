"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
export default function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false); const router = useRouter();
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    try { const response = await fetch(`/api/auth/${mode}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email: data.get("email"), password: data.get("password") }) });
      if (!response.ok) { const body = await response.json(); setError(typeof body.detail === "string" ? body.detail : "Check your email and password (12-128 characters)."); return; }
      router.push("/dashboard"); router.refresh();
    } catch { setError("Unable to connect. Please try again."); } finally { setBusy(false); }
  }
  return <section className="mx-auto max-w-sm"><h1 className="mb-6 text-2xl font-bold">{mode === "login" ? "Log in" : "Create account"}</h1><form onSubmit={submit} className="space-y-5"><label className="block">Email<input name="email" type="email" autoComplete="email" required /></label><label className="block">Password<input name="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={12} maxLength={128} required /></label><p className="text-sm text-slate-600">Use 12-128 characters.</p>{error && <p role="alert" className="text-red-700">{error}</p>}<button disabled={busy} className="w-full rounded bg-blue-700 p-3 text-white disabled:opacity-50">{busy ? "Please wait..." : mode === "login" ? "Log in" : "Sign up"}</button></form><Link className="mt-5 block underline" href={mode === "login" ? "/signup" : "/login"}>{mode === "login" ? "Create an account" : "Already have an account?"}</Link></section>;
}
