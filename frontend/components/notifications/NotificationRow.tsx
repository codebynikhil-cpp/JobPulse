"use client";
import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { Bell, Check } from "lucide-react";
import type { Notice } from "@/types/product";
import { request } from "@/lib/client-api";
import {
  Button,
  DateText,
  ExternalLink,
  ScoreBadge,
} from "@/components/ui/primitives";
import { ErrorState, useToast } from "@/components/ui/feedback";
export default function NotificationRow({ notice }: { notice: Notice }) {
  const router = useRouter(),
    toast = useToast();
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function read() {
    setBusy(true);
    setError("");
    try {
      await request(`/api/notifications/${notice.id}`, "PATCH");
      toast("Notification marked read.");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to mark read.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <article className={`notice-row ${notice.is_read ? "" : "notice-unread"}`}>
      <span className="notice-icon" aria-hidden="true">
        <Bell size={18} />
      </span>
      <div className="notice-main">
        <div className="notice-meta">
          <span>
            {notice.kind === "changed_job"
              ? "Updated opportunity"
              : "New opportunity"}
          </span>
          <span>{notice.is_read ? "Read" : "Unread"}</span>
          <DateText value={notice.created_at} withTime />
        </div>
        <h2>{notice.job_title}</h2>
        <p>{notice.company_name}</p>
        <div className="profile-badges">
          {notice.matching_profiles.map((name) => (
            <span className="badge profile-badge" key={name}>
              {name}
            </span>
          ))}
        </div>
        <div className="notice-actions">
          <Link prefetch={false} href={`/jobs/${notice.job_id}`}>
            Open job
          </Link>
          <ExternalLink url={notice.apply_url}>Apply</ExternalLink>
          {!notice.is_read && (
            <Button variant="ghost" disabled={busy} onClick={read}>
              <Check size={15} aria-hidden="true" />
              {busy ? "Saving..." : "Mark read"}
            </Button>
          )}
          <span className="muted delivery-status">
            Email: {notice.delivery_status.replaceAll("_", " ")}
          </span>
        </div>
        {error && <ErrorState message={error} />}
      </div>
      <ScoreBadge score={notice.match_score} />
    </article>
  );
}
