import type { Job } from "@/types/product";
import { EmptyState } from "@/components/ui/primitives";
import JobRow from "./JobRow";
export default function JobList({
  jobs,
  title = "No matching jobs yet",
  description = "Create a profile and monitor companies, or adjust your filters.",
}: {
  jobs: Job[];
  title?: string;
  description?: string;
}) {
  return jobs.length ? (
    <div className="job-list">
      {jobs.map((job) => (
        <JobRow key={job.id} job={job} />
      ))}
    </div>
  ) : (
    <EmptyState
      title={title}
      description={description}
      href="/profiles"
      action="Manage profiles"
    />
  );
}
