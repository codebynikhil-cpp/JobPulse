import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, MapPin, BriefcaseBusiness } from "lucide-react";
import { serverApi } from "@/lib/session";
import type { Job } from "@/types/product";
import { DateText, ScoreBadge, StatusBadge } from "@/components/ui/primitives";
import JobActions from "@/components/jobs/JobActions";
import MatchExplanation from "@/components/jobs/MatchExplanation";
import { label } from "@/types/profile";
export default async function JobDetail({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) notFound();
  const response = await serverApi(`/api/jobs/${id}`);
  if (response.status === 404) notFound();
  if (!response.ok) throw new Error("Unable to load job");
  const job: Job = await response.json();
  return (
    <>
      <Link prefetch={false} className="back-link" href="/jobs">
        <ArrowLeft size={16} />
        Back to jobs
      </Link>
      <article className="job-detail">
        <header className="detail-header">
          <div className="company-name">{job.company_name}</div>
          <div className="job-title-line">
            <h1>{job.title}</h1>
            <ScoreBadge score={job.best_score} />
          </div>
          <div className="job-meta">
            <span>
              <MapPin size={16} />
              {job.location || "Location not specified"}
            </span>
            <span>
              <BriefcaseBusiness size={16} />
              {job.experience_text || "Experience not specified"}
            </span>
            {job.employment_type && <span>{label(job.employment_type)}</span>}
            <StatusBadge status={job.status} />
            <StatusBadge status={job.user_status} />
          </div>
          <p className="muted">
            {job.posted_at ? "Posted " : "Discovered "}
            <DateText value={job.posted_at || job.first_seen_at} />
          </p>
        </header>
        <div className="detail-cta">
          <JobActions
            id={job.id}
            status={job.user_status}
            url={job.application_url}
          />
        </div>
        <div className="detail-columns">
          <section className="detail-section job-description">
            <h2>About the role</h2>
            <div>
              {job.description ||
                "Visit the official career site for the full role description."}
            </div>
          </section>
          <MatchExplanation profiles={job.matched_profiles} />
        </div>
      </article>
    </>
  );
}
