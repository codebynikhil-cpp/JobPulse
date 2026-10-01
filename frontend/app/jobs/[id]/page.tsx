import { serverApi, requireUser } from "@/lib/session";
import { notFound } from "next/navigation";
import AccountNav from "@/components/AccountNav";
import JobActions from "@/components/JobActions";
export const dynamic = "force-dynamic";
export default async function JobDetail({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  await requireUser();
  const { id } = await params;
  const r = await serverApi(`/api/jobs/${id}`);
  if (r.status === 404) notFound();
  if (!r.ok) throw new Error("Unable to load job");
  const j = await r.json();
  return (
    <>
      <AccountNav />
      <article className="card">
        <p>{j.company_name}</p>
        <h1>{j.title}</h1>
        <p>
          {[j.location, j.employment_type, j.experience_text]
            .filter(Boolean)
            .join(" | ")}
        </p>
        <p>
          Job: {j.status} | Your status: {j.user_status} | Match {j.best_score}
        </p>
        {j.matched_profiles.map(
          (p: {
            profile_id: string;
            profile_name: string;
            score: number;
            match_reasons: string[];
          }) => (
            <section key={p.profile_id}>
              <h2>
                {p.profile_name} | {p.score}
              </h2>
              <ul>
                {p.match_reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </section>
          ),
        )}
        <p className="whitespace-pre-wrap">{j.description}</p>
        {/^https?:\/\//i.test(j.application_url) && (
          <a href={j.application_url} target="_blank" rel="noopener noreferrer">
            Apply on official site
          </a>
        )}
        <JobActions id={id} />
      </article>
    </>
  );
}
