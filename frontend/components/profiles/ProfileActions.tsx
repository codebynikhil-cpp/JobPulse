"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { changeProfile } from "@/lib/profile-api";

export default function ProfileActions({ id, name, active }: { id: string; name: string; active: boolean }) {
  const router = useRouter();
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function perform(remove: boolean) {
    setBusy(true); setError("");
    try {
      await changeProfile(id, remove ? "DELETE" : "PATCH", remove ? undefined : { active: !active });
      if (remove) router.push("/profiles");
      router.refresh(); setConfirm(false);
    } catch (error) { setError(error instanceof Error ? error.message : "Unable to update profile."); }
    finally { setBusy(false); }
  }
  return <div className="mt-4 space-y-3">
    <div className="flex gap-3"><button disabled={busy} onClick={() => perform(false)} className="rounded border px-3 py-2 disabled:opacity-50">{busy ? "Please wait..." : active ? "Deactivate" : "Activate"}</button><button disabled={busy} onClick={() => setConfirm(true)} className="rounded px-3 py-2 text-red-700 underline">Delete</button></div>
    {confirm && <div role="alertdialog" aria-label={`Delete ${name}`} className="rounded border border-red-200 bg-red-50 p-4"><p>Delete &quot;{name}&quot; and all its configuration? This cannot be undone.</p><div className="mt-3 flex gap-4"><button disabled={busy} onClick={() => perform(true)} className="rounded bg-red-700 px-3 py-2 text-white">Delete profile</button><button disabled={busy} onClick={() => setConfirm(false)} className="underline">Keep profile</button></div></div>}
    {error && <p role="alert" className="text-red-700">{error}</p>}
  </div>;
}
