import Link from "next/link";
import { load, pageNumber, type Search } from "@/lib/product-api";
import type { Profile } from "@/types/profile";
import { label } from "@/types/profile";
import type { Company } from "@/types/product";
import {
  EmptyState,
  PageHeader,
  Pagination,
  StatusBadge,
} from "@/components/ui/primitives";
import ProfileActions from "@/components/profiles/ProfileActions";
export default async function ProfilesPage({
  searchParams,
}: {
  searchParams: Promise<Search>;
}) {
  const page = pageNumber((await searchParams).page);
  const [profiles, companies] = await Promise.all([
    load<Profile[]>(`/api/profiles?limit=21&offset=${(page - 1) * 20}`),
    load<Company[]>("/api/subscriptions"),
  ]);
  return (
    <>
      <PageHeader
        title="Job search profiles"
        description="A focused search for every kind of opportunity."
        action={
          <Link
            prefetch={false}
            className="button button-primary"
            href="/profiles/new"
          >
            Create profile
          </Link>
        }
      />
      {profiles.length ? (
        <div className="profile-list">
          {profiles.slice(0, 20).map((profile) => (
            <article key={profile.id} className="profile-row">
              <div className="profile-row-header">
                <h2>
                  <Link prefetch={false} href={`/profiles/${profile.id}`}>
                    {profile.name}
                  </Link>
                </h2>
                <StatusBadge status={profile.active ? "active" : "inactive"} />
              </div>
              <p>{profile.description || "No description"}</p>
              <p>
                {profile.roles.map((role) => role.name).join(" / ") ||
                  "No roles yet"}
              </p>
              <div className="profile-badges">
                <span className="badge">{profile.skills.length} skills</span>
                <span className="badge">
                  {profile.locations.filter((item) => !item.excluded).length}{" "}
                  locations
                </span>
                <span className="badge">
                  {profile.work_modes.map(label).join(" / ") || "Any work mode"}
                </span>
                {profile.active && (
                  <span className="badge">
                    {
                      companies.filter((c) =>
                        c.subscribed_profile_ids.includes(profile.id),
                      ).length
                    }{" "}
                    monitored companies
                  </span>
                )}
              </div>
              <div className="profile-row-footer">
                <div className="profile-links">
                  <Link prefetch={false} href={`/profiles/${profile.id}`}>
                    View details
                  </Link>
                  <Link prefetch={false} href={`/profiles/${profile.id}/edit`}>
                    Edit
                  </Link>
                </div>
                <ProfileActions
                  id={profile.id}
                  name={profile.name}
                  active={profile.active}
                />
              </div>
            </article>
          ))}
        </div>
      ) : (
        <EmptyState
          title={
            page === 1
              ? "Create your first profile"
              : "No profiles on this page"
          }
          description="Choose your roles, skills, and work preferences. Refine them anytime."
          href={page === 1 ? "/profiles/new" : "/profiles"}
          action={page === 1 ? "Get started" : "Back to profiles"}
        />
      )}
      <Pagination page={page} hasNext={profiles.length > 20} />
    </>
  );
}
