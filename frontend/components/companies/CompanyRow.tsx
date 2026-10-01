"use client";
import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { request } from "@/lib/client-api";
import type { Company } from "@/types/product";
import type { Profile } from "@/types/profile";
import {
  Button,
  DateText,
  ExternalLink,
  StatusBadge,
} from "@/components/ui/primitives";
import { ErrorState, useToast } from "@/components/ui/feedback";
export default function CompanyRow({
  company,
  profiles,
}: {
  company: Company;
  profiles: Profile[];
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const router = useRouter(),
    toast = useToast();
  async function toggle(subscribed: boolean, profile_id?: string) {
    setBusy(true);
    setError("");
    try {
      await request("/api/subscriptions", "POST", {
        company_id: company.company_id,
        subscribed,
        ...(profile_id ? { profile_id } : {}),
      });
      toast("Monitoring updated.");
      router.refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to update monitoring.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <article className="company-row">
      <div className="company-overview">
        <div className="company-avatar" aria-hidden="true">
          {company.company_name.slice(0, 2).toUpperCase()}
        </div>
        <div>
          <h2>{company.company_name}</h2>
          <p className="muted">
            {company.is_subscribed
              ? `Monitoring: ${company.subscribed_profile_names.length} active profiles`
              : "Not monitoring"}
          </p>
        </div>
        <Button
          disabled={busy || (!company.is_subscribed && profiles.length === 0)}
          onClick={() => toggle(!company.is_subscribed)}
        >
          {busy
            ? "Updating..."
            : company.is_subscribed
              ? "Stop monitoring"
              : "Monitor company"}
        </Button>
      </div>
      <div className="company-source">
        <div>
          <span className="eyebrow">OFFICIAL CAREER SOURCE</span>
          <ExternalLink url={company.career_url}>
            Official career site
          </ExternalLink>
          {!company.career_url && (
            <p className="muted">Career link unavailable</p>
          )}
        </div>
        {company.is_subscribed && (
          <>
            <div>
              <span className="eyebrow">MONITORING HEALTH</span>
              <StatusBadge status={company.source_health || "unknown"} />
            </div>
            <div>
              <span className="eyebrow">LAST CHECKED</span>
              <DateText value={company.last_checked_at} withTime />
            </div>
            <Link
              prefetch={false}
              className="matching-count"
              href={`/jobs?company_id=${company.company_id}`}
            >
              <strong>{company.recent_matches_count}</strong> matching open jobs
            </Link>
          </>
        )}
      </div>
      {profiles.length > 0 && (
        <details className="profile-monitoring">
          <summary>Choose profiles to monitor</summary>
          <fieldset disabled={busy}>
            {profiles.map((profile) => (
              <label key={profile.id}>
                <input
                  type="checkbox"
                  checked={company.subscribed_profile_ids.includes(profile.id)}
                  onChange={(e) => toggle(e.target.checked, profile.id)}
                />
                {profile.name}
              </label>
            ))}
          </fieldset>
        </details>
      )}
      {profiles.length === 0 && (
        <p className="muted">
          <Link prefetch={false} href="/profiles">
            Activate a profile
          </Link>{" "}
          to start monitoring.
        </p>
      )}
      {error && <ErrorState message={error} />}
    </article>
  );
}
