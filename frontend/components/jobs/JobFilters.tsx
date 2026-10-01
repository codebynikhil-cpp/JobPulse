import { Search, SlidersHorizontal } from "lucide-react";
import type { Company } from "@/types/product";
import type { Profile } from "@/types/profile";
import { employmentTypes, label } from "@/types/profile";
import { Button } from "@/components/ui/primitives";
export default function JobFilters({
  values,
  companies,
  profiles,
  view,
}: {
  values: Record<string, string>;
  companies: Company[];
  profiles: Profile[];
  view: string;
}) {
  return (
    <form className="job-filters" action={`/${view.toLowerCase()}`}>
      <div className="filter-primary">
        <label className="search-field">
          <span className="sr-only">Title or keyword</span>
          <Search size={17} aria-hidden="true" />
          <input
            name="search"
            defaultValue={values.search}
            placeholder="Search titles or keywords"
          />
        </label>
        <label>
          <span className="sr-only">Profile</span>
          <select name="profile_id" defaultValue={values.profile_id || ""}>
            <option value="">All profiles</option>
            {profiles.map((p) => (
              <option value={p.id} key={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="sr-only">Company</span>
          <select name="company_id" defaultValue={values.company_id || ""}>
            <option value="">All companies</option>
            {companies.map((c) => (
              <option value={c.company_id} key={c.company_id}>
                {c.company_name}
              </option>
            ))}
          </select>
        </label>
        <Button variant="primary">Apply filters</Button>
      </div>
      <details
        className="advanced-filters"
        open={Object.keys(values).some(
          (k) =>
            !["search", "profile_id", "company_id", "page", "sort"].includes(k),
        )}
      >
        <summary>
          <SlidersHorizontal size={15} aria-hidden="true" />
          More filters
        </summary>
        <div className="filter-grid">
          <label>
            Location
            <input
              name="location"
              defaultValue={values.location}
              placeholder="City, region, or remote"
            />
          </label>
          <label>
            Minimum match score
            <input
              name="min_score"
              type="number"
              min="0"
              max="100"
              defaultValue={values.min_score}
              placeholder="Any score"
            />
          </label>
          <label>
            Employment
            <select
              name="employment_type"
              defaultValue={values.employment_type || ""}
            >
              <option value="">Any employment type</option>
              {employmentTypes.map((type) => (
                <option key={type} value={type}>
                  {label(type)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Discovered since
            <input
              name="discovered_after"
              type="date"
              defaultValue={values.discovered_after}
            />
          </label>
          <label>
            Job status
            <select
              name="job_status"
              defaultValue={
                values.job_status ?? (view === "Jobs" ? "open" : "")
              }
            >
              <option value="open">Open</option>
              <option value="closed">Closed</option>
              <option value="">All</option>
            </select>
          </label>
          {view === "Jobs" && (
            <label>
              Your status
              <select
                name="user_status"
                defaultValue={values.user_status || ""}
              >
                <option value="">Active feed</option>
                {["new", "saved", "applied", "ignored"].map((status) => (
                  <option key={status} value={status}>
                    {label(status)}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            Order within this page
            <select name="sort" defaultValue={values.sort || "newest"}>
              <option value="newest">Newest first</option>
              <option value="score">Highest match (this page)</option>
              <option value="company">Company A–Z (this page)</option>
            </select>
          </label>
        </div>
      </details>
      <div className="filter-footer">
        <span>Results are paginated newest first.</span>
        <a href={`/${view.toLowerCase()}`}>Clear filters</a>
      </div>
    </form>
  );
}
