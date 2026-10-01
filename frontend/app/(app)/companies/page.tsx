import { allProfiles, load } from "@/lib/product-api";
import type { Company } from "@/types/product";
import CompanyRow from "@/components/companies/CompanyRow";
import { EmptyState, PageHeader } from "@/components/ui/primitives";
export default async function Page() {
  const [companies, profiles] = await Promise.all([
    load<Company[]>("/api/subscriptions"),
    allProfiles(),
  ]);
  return (
    <>
      <PageHeader
        title="Companies"
        description="Follow official careers. Let your profiles find the relevant roles."
      />
      <div className="list-heading">
        <span>
          {companies.filter((c) => c.is_subscribed).length} monitored,{" "}
          {companies.length} available
        </span>
        <span>Monitoring is configured per active profile</span>
      </div>
      {companies.length ? (
        <div className="company-list">
          {companies.map((company) => (
            <CompanyRow
              key={company.company_id}
              company={company}
              profiles={profiles.filter((p) => p.active)}
            />
          ))}
        </div>
      ) : (
        <EmptyState
          title="No companies available"
          description="Company career sources will appear here when available."
        />
      )}
    </>
  );
}
