import Link from "next/link";
import { serverApi } from "@/lib/session";
import { Profile, label } from "@/types/profile";
import ProfileActions from "@/components/profiles/ProfileActions";

export default async function ProfilesPage({ searchParams }: { searchParams: Promise<{ page?: string }> }) {
  const raw = (await searchParams).page || "1";
  const page = /^\d+$/.test(raw) ? Math.min(Math.max(Number(raw), 1), 100000) : 1;
  const response = await serverApi(`/api/profiles?limit=21&offset=${(page - 1) * 20}`);
  if (!response.ok) throw new Error("Unable to load profiles");
  const results: Profile[] = await response.json();
  const profiles = results.slice(0, 20);
  return <>
    <div className="mb-8 flex flex-wrap items-center justify-between gap-4"><div><h1 className="text-3xl font-bold">Job search profiles</h1><p className="mt-2 text-slate-600">Keep a separate profile for each kind of opportunity.</p></div><Link href="/profiles/new" className="rounded bg-blue-700 px-4 py-3 font-medium text-white">Create profile</Link></div>
    {profiles.length === 0 ? <div className="rounded-xl border border-dashed bg-white p-10 text-center"><h2 className="text-xl font-semibold">{page === 1 ? "Create your first profile" : "No profiles on this page"}</h2><p className="my-3 text-slate-600">Choose your roles, skills and work preferences. You can refine them anytime.</p><Link href={page === 1 ? "/profiles/new" : "/profiles"} className="text-blue-700 underline">{page === 1 ? "Get started" : "Back to profiles"}</Link></div> : <div className="space-y-5">{profiles.map((profile) => <article key={profile.id} className="rounded-xl border bg-white p-6"><div className="flex items-start justify-between gap-4"><div><Link href={`/profiles/${profile.id}`} className="text-xl font-semibold text-blue-800 underline">{profile.name}</Link><p className="mt-2 whitespace-pre-wrap text-slate-600">{profile.description || "No description"}</p></div><span className={`rounded-full px-3 py-1 text-sm ${profile.active ? "bg-green-100 text-green-800" : "bg-slate-100 text-slate-600"}`}>{profile.active ? "Active" : "Inactive"}</span></div><p className="mt-4 text-sm">{profile.roles.map((role) => role.name).join(" / ") || "No roles yet"}</p><p className="mt-2 text-sm text-slate-600">{profile.skills.length} skills &middot; {profile.locations.filter((item) => !item.excluded).length} locations &middot; {profile.work_modes.map(label).join(" / ") || "Any work mode"}</p><div className="mt-4 flex gap-5"><Link href={`/profiles/${profile.id}`} className="underline">View details</Link><Link href={`/profiles/${profile.id}/edit`} className="underline">Edit</Link></div><ProfileActions id={profile.id} name={profile.name} active={profile.active} /></article>)}</div>}
    <nav aria-label="Profile pages" className="mt-8 flex gap-6">{page > 1 && <Link href={`/profiles?page=${page - 1}`} className="underline">Previous</Link>}{results.length > 20 && <Link href={`/profiles?page=${page + 1}`} className="underline">Next</Link>}</nav>
  </>;
}
