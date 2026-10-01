"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
export default function JobActions({ id }: { id: string }) {
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const router = useRouter();
  return (
    <>
      <div className="actions">
        {["saved", "applied", "ignored", "new"].map((status) => (
          <button
            disabled={busy}
            key={status}
            onClick={async () => {
              setBusy(true);
              try {
                const r = await fetch(`/api/jobs/${id}/status`, {
                  method: "PATCH",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ status }),
                });
                if (!r.ok) throw new Error();
                setMessage("Change saved.");
                router.refresh();
              } catch {
                setMessage("Unable to save change. Please retry.");
              } finally {
                setBusy(false);
              }
            }}
          >
            {status === "new"
              ? "Restore"
              : status === "applied"
                ? "Mark applied"
                : status === "saved"
                  ? "Save"
                  : "Ignore"}
          </button>
        ))}
      </div>
      <p role="status">{message}</p>
    </>
  );
}
