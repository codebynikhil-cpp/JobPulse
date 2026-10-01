"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { changeProfile } from "@/lib/profile-api";
import { Button } from "@/components/ui/primitives";
import { ConfirmDialog, ErrorState, useToast } from "@/components/ui/feedback";
export default function ProfileActions({
  id,
  name,
  active,
}: {
  id: string;
  name: string;
  active: boolean;
}) {
  const router = useRouter(),
    toast = useToast();
  const [confirm, setConfirm] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function perform(remove: boolean) {
    setBusy(true);
    setError("");
    try {
      await changeProfile(
        id,
        remove ? "DELETE" : "PATCH",
        remove ? undefined : { active: !active },
      );
      toast(
        remove
          ? "Profile deleted."
          : active
            ? "Profile deactivated."
            : "Profile activated.",
      );
      if (remove) router.push("/profiles");
      router.refresh();
      setConfirm(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to update profile.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <div className="profile-actions">
        <Button disabled={busy} onClick={() => perform(false)}>
          {busy ? "Please wait..." : active ? "Deactivate" : "Activate"}
        </Button>
        <Button
          variant="ghost"
          disabled={busy}
          onClick={() => {
            setError("");
            setConfirm(true);
          }}
        >
          Delete
        </Button>
      </div>
      {error && !confirm && <ErrorState message={error} />}
      <ConfirmDialog
        open={confirm}
        onOpenChange={setConfirm}
        title={`Delete ${name}?`}
        description="This removes the profile and all its configuration. This cannot be undone."
        onConfirm={() => perform(true)}
        busy={busy}
        error={error}
      />
    </div>
  );
}
