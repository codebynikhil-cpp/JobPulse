import Link from "next/link";
import { MapPin, BriefcaseBusiness } from "lucide-react";
import type { Job } from "@/types/product";
import { DateText, ScoreBadge, StatusBadge } from "@/components/ui/primitives";
import JobActions from "./JobActions";
import { label } from "@/types/profile";
export default function JobRow({ job }: { job: Job }) {
  return (
    <article className="job-row">
      <div className="company-avatar" aria-hidden="true">
        {job.company_name.slice(0, 2).toUpperCase()}
      </div>
      <div className="job-main">
        <div className="job-topline">
          <span className="company-name">{job.company_name}</span>
          <span className="job-date">
            {job.posted_at ? "Posted " : "Discovered "}
            <DateText value={job.posted_at || job.first_seen_at} />
          </span>
        </div>
        <div className="job-title-line">
          <h2>
            <Link prefetch={false} href={`/jobs/${job.id}`}>
              {job.title}
            </Link>
          </h2>
          <ScoreBadge score={job.best_score} />
        </div>
        <div className="job-meta">
          <span>
            <MapPin size={14} aria-hidden="true" />
            {job.location || "Location not specified"}
          </span>
          <span>
            <BriefcaseBusiness size={14} aria-hidden="true" />
            {job.experience_text || "Experience not specified"}
          </span>
          {job.employment_type && <span>{label(job.employment_type)}</span>}
          <StatusBadge status={job.status} />
          {job.user_status !== "new" && (
            <StatusBadge status={job.user_status} />
          )}
        </div>
        <div className="profile-badges">
          {job.matched_profiles.map((profile) => (
            <Link
              prefetch={false}
              className="badge profile-badge"
              href={`/profiles/${profile.profile_id}`}
              key={profile.profile_id}
            >
              {profile.profile_name}
              <span>{Math.round(profile.score)}</span>
            </Link>
          ))}
        </div>
        <JobActions
          id={job.id}
          status={job.user_status}
          url={job.application_url}
        />
      </div>
    </article>
  );
}
