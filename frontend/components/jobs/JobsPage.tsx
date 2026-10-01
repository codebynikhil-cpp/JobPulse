import {
  allProfiles,
  load,
  pageNumber,
  queryValues,
  type Search,
} from "@/lib/product-api";
import type { Company, Feed } from "@/types/product";
import { PageHeader, Pagination } from "@/components/ui/primitives";
import JobFilters from "./JobFilters";
import JobList from "./JobList";
export default async function JobsPage({
  view,
  searchParams,
}: {
  view: "Jobs" | "Saved" | "Applied";
  searchParams: Promise<Search>;
}) {
  const values = queryValues(await searchParams),
    page = pageNumber(values.page);
  const allowed = [
    "search",
    "profile_id",
    "company_id",
    "location",
    "min_score",
    "employment_type",
    "discovered_after",
    "job_status",
    "user_status",
  ];
  const query = new URLSearchParams({ page: String(page), page_size: "20" });
  for (const key of allowed)
    if (values[key] || (key === "job_status" && values[key] !== undefined))
      query.set(key, values[key]);
  if (view !== "Jobs") {
    query.set("user_status", view.toLowerCase());
    if (values.job_status === undefined) query.set("job_status", "");
  }
  const [feed, profiles, companies] = await Promise.all([
    load<Feed>(`/api/jobs?${query}`),
    allProfiles(),
    load<Company[]>("/api/subscriptions"),
  ]);
  const jobs = [...feed.items];
  if (values.sort === "score") jobs.sort((a, b) => b.best_score - a.best_score);
  if (values.sort === "company")
    jobs.sort((a, b) => a.company_name.localeCompare(b.company_name));
  return (
    <>
      <PageHeader
        title={view}
        description={
          view === "Jobs"
            ? "Opportunities matched to the way you want to work."
            : view === "Saved"
              ? "Your shortlist. Take the next step when you’re ready."
              : "Keep track of the opportunities you’ve pursued."
        }
      />
      <JobFilters
        key={JSON.stringify(values)}
        values={values}
        companies={companies}
        profiles={profiles}
        view={view}
      />
      <div className="list-heading">
        <span>
          <strong>{feed.total}</strong> matching jobs
        </span>
        <span>Official company careers</span>
      </div>
      <JobList
        jobs={jobs}
        title={
          view === "Jobs"
            ? "No matching jobs"
            : `No ${view.toLowerCase()} jobs yet`
        }
        description={
          view === "Jobs"
            ? "Try broader filters, or check your profiles and monitored companies."
            : `Jobs you mark ${view.toLowerCase()} appear here, including closed roles.`
        }
      />
      <Pagination page={page} totalPages={feed.total_pages} query={values} />
    </>
  );
}
