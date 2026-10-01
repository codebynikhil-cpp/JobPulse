import Link from "next/link";
import { ArrowRight, Activity, Bookmark, CheckCheck } from "lucide-react";
import type { Overview } from "@/types/product";
import {
  DateText,
  EmptyState,
  PageHeader,
  StatusBadge,
} from "@/components/ui/primitives";
import JobList from "@/components/jobs/JobList";
import NotificationRow from "@/components/notifications/NotificationRow";
export default function Dashboard({ data }: { data: Overview }) {
  const stats = data.stats;
  return (
    <>
      <PageHeader
        title="Dashboard"
        description="A clear view of your next move."
        action={
          <Link
            prefetch={false}
            className="button button-secondary"
            href="/profiles"
          >
            Manage profiles
            <ArrowRight size={15} />
          </Link>
        }
      />
      <div className="dashboard-summary">
        <div className="summary-primary">
          <span className="eyebrow">YOUR OPPORTUNITIES</span>
          <p>
            <strong>{stats.new_jobs_count}</strong> new matching jobs
          </p>
          <span className="muted">
            Across {stats.monitored_companies_count} monitored companies and{" "}
            {stats.active_profiles_count} active profiles
          </span>
        </div>
        <Link prefetch={false} href="/saved">
          <Bookmark size={18} />
          <strong>{stats.saved_jobs_count}</strong>
          <span>Saved</span>
        </Link>
        <Link prefetch={false} href="/applied">
          <CheckCheck size={18} />
          <strong>{stats.applied_jobs_count}</strong>
          <span>Applied</span>
        </Link>
      </div>
      {stats.active_profiles_count === 0 && (
        <div className="onboarding">
          <Activity size={22} />
          <div>
            <h2>Make your search personal</h2>
            <p>Create an active profile, then choose companies to monitor.</p>
          </div>
          <Link
            prefetch={false}
            className="button button-primary"
            href="/profiles/new"
          >
            Create profile
          </Link>
        </div>
      )}
      <div className="dashboard-grid">
        <section>
          <div className="section-heading">
            <div>
              <span className="eyebrow">MATCHED TO YOU</span>
              <h2>Recent matching jobs</h2>
            </div>
            <Link prefetch={false} href="/jobs">
              View all
              <ArrowRight size={15} />
            </Link>
          </div>
          <JobList jobs={data.recent_jobs.slice(0, 5)} />
          <div className="section-heading section-spaced">
            <div>
              <span className="eyebrow">STAY IN THE LOOP</span>
              <h2>Recent notifications</h2>
            </div>
            <Link prefetch={false} href="/notifications">
              View all
              <ArrowRight size={15} />
            </Link>
          </div>
          {data.recent_notifications.length ? (
            <div className="notice-list">
              {data.recent_notifications.slice(0, 3).map((notice) => (
                <NotificationRow notice={notice} key={notice.id} />
              ))}
            </div>
          ) : (
            <EmptyState
              title="You’re all caught up"
              description="New matching opportunities will appear here."
            />
          )}
        </section>
        <aside className="monitoring-panel">
          <div className="section-heading">
            <h2>Monitoring</h2>
            <Activity size={18} />
          </div>
          <p className="muted">Keeping an eye on official careers.</p>
          <div className="health-summary">
            {Object.entries(data.source_health_summary)
              .filter(([, count]) => count > 0)
              .map(([key, count]) => (
                <div key={key}>
                  <StatusBadge status={key.replace("_count", "")} />
                  <strong>{count}</strong>
                </div>
              ))}
          </div>
          {data.monitored_companies.slice(0, 5).map((company) => (
            <div className="monitoring-company" key={company.company_id}>
              <Link
                prefetch={false}
                href={`/jobs?company_id=${company.company_id}`}
              >
                {company.company_name}
              </Link>
              <StatusBadge status={company.source_health || "unknown"} />
              <small>
                Checked <DateText value={company.last_checked_at} withTime />
              </small>
            </div>
          ))}
          {stats.monitored_companies_count === 0 && (
            <p className="muted">Choose companies to start monitoring.</p>
          )}
          <Link
            prefetch={false}
            className="button button-secondary"
            href="/companies"
          >
            Manage companies
            <ArrowRight size={15} />
          </Link>
          <div className="quiet-note">
            <h3>Your search stays yours</h3>
            <p>
              Matches follow your profiles. Save the roles you like, and ignore
              those you don’t.
            </p>
            <Link prefetch={false} href="/jobs?user_status=ignored">
              Review ignored jobs
            </Link>
          </div>
        </aside>
      </div>
    </>
  );
}
