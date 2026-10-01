"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
export default function Logout() { const router = useRouter(); const [error, setError] = useState(""); return <><button className="mt-6 rounded border px-4 py-2" onClick={async () => { try { const result = await fetch("/api/auth/logout", { method: "POST" }); if (!result.ok) throw new Error(); router.push("/login"); router.refresh(); } catch { setError("Logout failed. Please retry."); } }}>Log out</button>{error && <p role="alert">{error}</p>}</>; }
