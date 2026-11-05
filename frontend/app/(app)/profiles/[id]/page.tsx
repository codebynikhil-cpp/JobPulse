import Link from "next/link";
import { loadProfile } from "@/lib/load-profile";
import { label } from "@/types/profile";
import { PageHeader } from "@/components/ui/primitives";
import ProfileActions from "@/components/profiles/ProfileActions";
function Items({ values }: { values: string[] }) {
  return values.length ? (
    <ul className="mt-2 flex flex-wrap gap-2">
      {values.map((value) => (
        <li className="badge profile-badge" key={value}>
          {value}
        </li>
      ))}
    </ul>
  ) : (
    <p className="mt-2 text-sm text-muted">None specified</p>
  );
}
export default async function ProfileDetails({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const profile = await loadProfile((await params).id);
  return (
    <>
      <PageHeader
        title={profile.name}
        description={
          profile.active
            ? "Active job search profile"
            : "Inactive job search profile"
        }
        action={
          <Link
            prefetch={false}
            href={`/profiles/${profile.id}/edit`}
            className="button button-primary"
          >
            Edit profile
          </Link>
        }
      />
      <p className="mb-8 whitespace-pre-wrap text-foreground">
        {profile.description || "No description provided."}
      </p>
      <div className="profile-detail-grid">
        <section>
          <h2 className="text-2xl font-black">Target roles</h2>
          <Items values={profile.roles.map((item) => item.name)} />
          <h3 className="mt-5 font-medium">Experience</h3>
          <p className="mt-2">
            {profile.exp_min === null && profile.exp_max === null
              ? "No experience preference"
              : `${profile.exp_min ?? "0"} to ${profile.exp_max ?? "any"} years`}
          </p>
        </section>
        <section>
          <h2 className="text-2xl font-black">Skills</h2>
          <h3 className="mt-4 font-medium">Required</h3>
          <Items
            values={profile.skills
              .filter((item) => item.kind === "required")
              .map((item) => item.name)}
          />
          <h3 className="mt-4 font-medium">Preferred</h3>
          <Items
            values={profile.skills
              .filter((item) => item.kind === "preferred")
              .map((item) => item.name)}
          />
        </section>
        <section>
          <h2 className="text-2xl font-black">Work preferences</h2>
          <h3 className="mt-4 font-medium">Employment</h3>
          <Items
            values={
              profile.employment_types.length
                ? profile.employment_types.map(label)
                : ["Any employment type"]
            }
          />
          <h3 className="mt-4 font-medium">Work mode</h3>
          <Items
            values={
              profile.work_modes.length
                ? profile.work_modes.map(label)
                : ["Any work mode"]
            }
          />
          <h3 className="mt-4 font-medium">Locations</h3>
          <Items
            values={profile.locations
              .filter((item) => !item.excluded)
              .map((item) => item.name)}
          />
        </section>
        <section>
          <h2 className="text-2xl font-black">Exclusions</h2>
          <h3 className="mt-4 font-medium">Keywords</h3>
          <Items
            values={profile.exclusions
              .filter((item) => item.kind === "keyword")
              .map((item) => item.term)}
          />
          <h3 className="mt-4 font-medium">Roles</h3>
          <Items
            values={profile.exclusions
              .filter((item) => item.kind === "role")
              .map((item) => item.term)}
          />
          <h3 className="mt-4 font-medium">Locations</h3>
          <Items
            values={profile.locations
              .filter((item) => item.excluded)
              .map((item) => item.name)}
          />
        </section>
      </div>
      <ProfileActions
        id={profile.id}
        name={profile.name}
        active={profile.active}
      />
    </>
  );
}
