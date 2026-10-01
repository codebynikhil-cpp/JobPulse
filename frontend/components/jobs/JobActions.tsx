"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Bookmark, CheckCheck, EyeOff, RotateCcw } from "lucide-react";
import { request } from "@/lib/client-api";
import { Button, ExternalLink } from "@/components/ui/primitives";
import { ErrorState, useToast } from "@/components/ui/feedback";
export default function JobActions({
  id,
  status,
  url,
}: {
  id: string;
  status: string;
  url: string;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const router = useRouter(),
    toast = useToast();
  async function change(next: string) {
    setBusy(true);
    setError("");
    try {
      await request(`/api/jobs/${id}/status`, "PATCH", { status: next });
      toast("Change saved.");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to save change.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="job-action-wrap">
      <div className="job-actions">
        <ExternalLink url={url} primary>
          Apply on official site
        </ExternalLink>
        <Button
          disabled={busy || status === "saved"}
          onClick={() => change("saved")}
        >
          <Bookmark size={15} aria-hidden="true" />
          {status === "saved" ? "Saved" : "Save"}
        </Button>
        <Button
          disabled={busy || status === "applied"}
          onClick={() => change("applied")}
        >
          <CheckCheck size={15} aria-hidden="true" />
          {status === "applied" ? "Applied" : "Mark applied"}
        </Button>
        {status !== "ignored" ? (
          <Button
            variant="ghost"
            disabled={busy}
            onClick={() => change("ignored")}
          >
            <EyeOff size={15} aria-hidden="true" />
            Ignore
          </Button>
        ) : (
          <Button disabled={busy} onClick={() => change("new")}>
            <RotateCcw size={15} aria-hidden="true" />
            Restore
          </Button>
        )}
        {status !== "new" && status !== "ignored" && (
          <Button variant="ghost" disabled={busy} onClick={() => change("new")}>
            Restore
          </Button>
        )}
      </div>
      {error && <ErrorState message={error} />}
    </div>
  );
}
