"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { request } from "@/lib/client-api";
import { Button } from "@/components/ui/primitives";
import { ErrorState, useToast } from "@/components/ui/feedback";
export default function ReadAllButton() {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const router = useRouter(),
    toast = useToast();
  return (
    <div>
      <Button
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setError("");
          try {
            await request("/api/notifications/read-all", "PATCH");
            toast("All notifications marked read.");
            router.refresh();
          } catch (e) {
            setError(
              e instanceof Error ? e.message : "Unable to mark all read.",
            );
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "Saving…" : "Mark all read"}
      </Button>
      {error && <ErrorState message={error} />}
    </div>
  );
}
