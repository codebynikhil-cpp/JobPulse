"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import Logout from "@/components/Logout";
type Profile = {
  profile_id: string;
  profile_name: string;
  score: number;
  match_reasons: string[];
};
type Job = {
  id: string;
  company_name: string;
  title: string;
  location: string;
  employment_type: string | null;
  experience_text: string | null;
  posted_at: string | null;
  first_seen_at: string;
  application_url: string;
  status: string;
  user_status: string;
  best_score: number;
  matched_profiles: Profile[];
  match_reasons: string[];
};
type Notice = {
  id: string;
  job_id: string;
  company_name: string;
  job_title: string;
  kind: string;
  match_score: number;
  matching_profiles: string[];
  delivery_status: string;
  is_read: boolean;
  created_at: string;
  apply_url: string | null;
};
type Company = {
  company_id: string;
  company_name: string;
  career_url: string | null;
  is_subscribed: boolean;
  source_health: string | null;
  last_checked_at: string | null;
  last_success_at: string | null;
  acquisition_method: string | null;
  recent_failure: boolean;
  recent_matches_count: number;
};
type Feed = { items: Job[]; total: number; total_pages: number };
type Overview = {
  stats: Record<string, number>;
  source_health_summary: Record<string, number>;
  recent_jobs: Job[];
  recent_notifications: Notice[];
};
const date = (value: string | null) =>
  value ? new Date(value).toLocaleString() : "Not available";
function External({
  url,
  children,
}: {
  url: string | null;
  children: React.ReactNode;
}) {
  return url && /^https?:\/\//i.test(url) ? (
    <a
      className="btn btn-secondary"
      href={url}
      target="_blank"
      rel="noopener noreferrer"
    >
      {children}
    </a>
  ) : null;
}
export default function Workspace({ view }: { view: string }) {
  const [data, setData] = useState<Overview | null>(null),
    [feed, setFeed] = useState<Feed | null>(null),
    [notices, setNotices] = useState<Notice[]>([]),
    [companies, setCompanies] = useState<Company[]>([]),
    [profiles, setProfiles] = useState<{ id: string; name: string }[]>([]);
  const [page, setPage] = useState(1),
    [filters, setFilters] = useState<Record<string, string>>(() =>
      typeof window === "undefined"
        ? {}
        : Object.fromEntries(new URLSearchParams(window.location.search)),
    ),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [message, setMessage] = useState(""),
    [revision, setRevision] = useState(0),
    [busy, setBusy] = useState(false);
  const isJobs = ["Jobs", "Saved", "Applied"].includes(view);
  useEffect(() => {
    let alive = true;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const params = new URLSearchParams({
          page: String(page),
          page_size: "20",
        });
        Object.entries(filters).forEach(([k, v]) => {
          if (v) params.set(k, v);
        });
        if (view === "Saved" || view === "Applied") {
          params.set("user_status", view.toLowerCase());
          params.set("job_status", "");
        }
        const path = isJobs
          ? `/api/jobs?${params}`
          : view === "Notifications"
            ? `/api/notifications?limit=20&offset=${(page - 1) * 20}`
            : view === "Companies"
              ? "/api/subscriptions"
              : "/api/dashboard";
        const res = await fetch(path);
        if (!res.ok)
          throw new Error(
            res.status === 401
              ? "Your session expired. Please sign in."
              : "Unable to load this page. Try again.",
          );
        const result = await res.json();
        if (!alive) return;
        if (isJobs) setFeed(result);
        else if (view === "Notifications") setNotices(result);
        else if (view === "Companies") setCompanies(result);
        else setData(result);
      } catch (e) {
        if (alive)
          setError(e instanceof Error ? e.message : "Service unavailable");
      } finally {
        if (alive) setLoading(false);
      }
    }
    load();
    return () => {
      alive = false;
    };
  }, [view, page, filters, revision, isJobs]);
  useEffect(() => {
    if (!isJobs) return;
    Promise.all([fetch("/api/profiles"), fetch("/api/subscriptions")])
      .then(async ([p, c]) => {
        if (p.ok) setProfiles(await p.json());
        if (c.ok) setCompanies(await c.json());
      })
      .catch(() => setError("Filter options unavailable. Try again."));
  }, [isJobs]);
  async function action(path: string, body?: unknown) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const res = await fetch(path, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!res.ok) throw new Error("Unable to save your change. Try again.");
      setMessage("Change saved.");
      setRevision((v) => v + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to save");
    } finally {
      setBusy(false);
    }
  }
  function jobs(items: Job[]) {
    return items.length ? (
      items.map((j) => (
        <article className="card" key={j.id}>
          <div className="row-sb">
            <div>
              <p className="text-muted">{j.company_name}</p>
              <h2 className="section-title">{j.title}</h2>
            </div>
            <span className="badge">Match {j.best_score}</span>
          </div>
          <p>
            {[j.location, j.employment_type, j.experience_text]
              .filter(Boolean)
              .join(" | ")}
          </p>
          <p className="text-sm">
            Job: {j.status} | Your status: {j.user_status}
          </p>
          <p className="text-xs text-muted">
            {j.posted_at
              ? `Posted ${date(j.posted_at)}`
              : `Discovered ${date(j.first_seen_at)}`}
          </p>
          {j.matched_profiles.map((p) => (
            <details key={p.profile_id}>
              <summary>
                {p.profile_name} | {p.score}
              </summary>
              <ul>
                {p.match_reasons.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </details>
          ))}
          <div className="actions">
            <External url={j.application_url}>Apply on career site</External>
            {["saved", "applied", "ignored", "new"].map((status) => (
              <button
                className="btn btn-secondary"
                disabled={busy || j.user_status === status}
                key={status}
                onClick={() => action(`/api/jobs/${j.id}/status`, { status })}
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
        </article>
      ))
    ) : (
      <p className="empty">
        {view === "Saved"
          ? "No saved jobs yet."
          : view === "Applied"
            ? "No applied jobs yet."
            : "No matching jobs. Create a profile and monitor companies, or adjust your filters."}
      </p>
    );
  }
  function notifications(items: Notice[]) {
    return items.length ? (
      items.map((n) => (
        <article className="card" key={n.id}>
          <h2>
            {n.company_name} | {n.job_title}
          </h2>
          <p>
            {n.kind === "changed_job" ? "Changed job" : "New job"} | Match{" "}
            {n.match_score} | {n.is_read ? "Read" : "Unread"}
          </p>
          <p>{n.matching_profiles.join(", ")}</p>
          <p className="text-muted">
            {date(n.created_at)} | Email:{" "}
            {n.delivery_status.replaceAll("_", " ")}
          </p>
          <div className="actions">
            <Link href={`/jobs/${n.job_id}`}>Open job</Link>
            <External url={n.apply_url}>Apply</External>
            {!n.is_read && (
              <button
                disabled={busy}
                onClick={() => action(`/api/notifications/${n.id}`)}
              >
                Mark read
              </button>
            )}
          </div>
        </article>
      ))
    ) : (
      <p className="empty">No notifications yet.</p>
    );
  }
  return (
    <>
      <nav className="workspace-nav" aria-label="Account navigation">
        {[
          "Dashboard",
          "Jobs",
          "Saved",
          "Applied",
          "Notifications",
          "Profiles",
          "Companies",
          "Account",
        ].map((v) => (
          <Link
            aria-current={v === view ? "page" : undefined}
            key={v}
            href={`/${v.toLowerCase()}`}
          >
            {v}
          </Link>
        ))}
      </nav>
      <h1 className="page-title">{view}</h1>
      {error && (
        <p role="alert">
          {error}{" "}
          <button onClick={() => setRevision((v) => v + 1)}>Retry</button>{" "}
          <Link href="/login">Sign in</Link>
        </p>
      )}
      {message && <p role="status">{message}</p>}
      {isJobs && (
        <form
          className="filters"
          onSubmit={(e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            setFilters(
              Object.fromEntries(
                [...f.entries()].map(([k, v]) => [k, String(v)]),
              ),
            );
            setPage(1);
          }}
        >
          <label>
            Title or keyword
            <input name="search" />
          </label>
          <label>
            Location
            <input name="location" />
          </label>
          <label>
            Profile
            <select name="profile_id">
              <option value="">All profiles</option>
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Company
            <select name="company_id">
              <option value="">All companies</option>
              {companies.map((c) => (
                <option key={c.company_id} value={c.company_id}>
                  {c.company_name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Minimum score
            <input name="min_score" type="number" min="0" max="100" />
          </label>
          <label>
            Employment type
            <input name="employment_type" placeholder="e.g. full_time" />
          </label>
          <label>
            Discovered since
            <input name="discovered_after" type="date" />
          </label>
          <label>
            Job status
            <select name="job_status">
              <option value="open">Open</option>
              <option value="closed">Closed</option>
              <option value="">All</option>
            </select>
          </label>
          {view === "Jobs" && (
            <label>
              Your status
              <select name="user_status">
                <option value="">Active feed</option>
                {["new", "saved", "applied", "ignored"].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </select>
            </label>
          )}
          <button className="btn btn-primary">Apply filters</button>
        </form>
      )}
      {loading ? (
        <p role="status">Loading {view.toLowerCase()}...</p>
      ) : (
        <>
          {isJobs && feed && (
            <>
              <p>{feed.total} matching jobs</p>
              {jobs(feed.items)}
              <div className="pagination">
                <button
                  disabled={page === 1}
                  onClick={() => setPage((p) => p - 1)}
                >
                  Previous
                </button>
                <span>
                  Page {page} of {Math.max(1, feed.total_pages)}
                </span>
                <button
                  disabled={page >= feed.total_pages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </button>
              </div>
            </>
          )}
          {view === "Notifications" && (
            <>
              <button
                disabled={busy || !notices.some((n) => !n.is_read)}
                onClick={() => action("/api/notifications/read-all")}
              >
                Mark all read
              </button>
              {notifications(notices)}
              <div className="pagination">
                <button
                  disabled={page === 1}
                  onClick={() => setPage((p) => p - 1)}
                >
                  Previous
                </button>
                <span>Page {page}</span>
                <button
                  disabled={notices.length < 20}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </button>
              </div>
            </>
          )}
          {view === "Companies" &&
            (companies.length ? (
              companies.map((c) => (
                <article className="card" key={c.company_id}>
                  <h2>{c.company_name}</h2>
                  <p>
                    {c.is_subscribed ? "Monitoring" : "Inactive subscription"}
                  </p>
                  {c.is_subscribed && (
                    <>
                      <p>
                        Source: {c.source_health} | {c.acquisition_method}
                        {c.recent_failure ? " | Recent check failed" : ""}
                      </p>
                      <p>
                        Last checked: {date(c.last_checked_at)}
                        <br />
                        Last success: {date(c.last_success_at)}
                      </p>
                      <p>{c.recent_matches_count} matching open jobs</p>
                    </>
                  )}
                  <External url={c.career_url}>Official career site</External>
                  <button
                    disabled={busy}
                    onClick={async () => {
                      setBusy(true);
                      try {
                        const r = await fetch("/api/subscriptions", {
                          method: "POST",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({
                            company_id: c.company_id,
                            subscribed: !c.is_subscribed,
                          }),
                        });
                        if (!r.ok)
                          throw new Error(
                            "Create an active profile before monitoring, then try again.",
                          );
                        setRevision((v) => v + 1);
                        setMessage("Subscription updated.");
                      } catch (e) {
                        setError(
                          e instanceof Error ? e.message : "Unable to update",
                        );
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    {c.is_subscribed ? "Stop monitoring" : "Monitor company"}
                  </button>
                </article>
              ))
            ) : (
              <p className="empty">No companies available.</p>
            ))}
          {view === "Dashboard" && data && (
            <>
              <div className="dashboard-stats card-grid card-grid-3">
                {Object.entries(data.stats).map(([key, value]) => (
                  <Link
                    className="card"
                    key={key}
                    href={
                      key.includes("profiles")
                        ? "/profiles"
                        : key.includes("companies")
                          ? "/companies"
                          : key.includes("notifications")
                            ? "/notifications"
                            : key.includes("saved")
                              ? "/saved"
                              : key.includes("applied")
                                ? "/applied"
                                : key.includes("ignored")
                                  ? "/jobs?user_status=ignored"
                                  : "/jobs"
                    }
                  >
                    <strong>{value}</strong>
                    <p>{key.replaceAll("_", " ").replace(" count", "")}</p>
                  </Link>
                ))}
              </div>
              <h2>Source health</h2>
              <p>
                {Object.entries(data.source_health_summary)
                  .map(([k, v]) => `${k.replace("_count", "")}: ${v}`)
                  .join(" | ")}
              </p>
              <Link href="/companies">Manage monitoring</Link>
              <h2>Recent matching jobs</h2>
              {jobs(data.recent_jobs)}
              <h2>Recent notifications</h2>
              {notifications(data.recent_notifications)}
            </>
          )}
        </>
      )}
      <Logout />
    </>
  );
}
