import Link from "next/link";
import { loadProfile } from "@/lib/load-profile";
import { label } from "@/types/profile";
import ProfileActions from "@/components/profiles/ProfileActions";
function Items({ values }: { values: string[] }) {
  return values.length ? <ul className="mt-2 flex flex-wrap gap-2">{values.map((value) => <li className="rounded bg-slate-100 px-3 py-1 text-sm" key={value}>{value}</li>)}</ul> : <p className="mt-2 text-sm text-slate-500">None specified</p>;
}
export default async function ProfileDetails({ params }: { params: Promise<{ id: string }> }) {
  const profile = await loadProfile((await params).id);
  return <>
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4"><div><p className="mb-2 text-sm font-medium text-slate-600">{profile.active ? "Active" : "Inactive"} profile</p><h1 className="text-3xl font-bold">{profile.name}</h1></div><Link href={`/profiles/${profile.id}/edit`} className="rounded bg-blue-700 px-5 py-3 text-white">Edit profile</Link></div>
    <p className="mb-8 whitespace-pre-wrap text-slate-600">{profile.description || "No description provided."}</p>
    <div className="grid gap-6 sm:grid-cols-2">
      <section className="rounded-xl border bg-white p-6"><h2 className="text-lg font-semibold">Target roles</h2><Items values={profile.roles.map((item) => item.name)} /><h3 className="mt-5 font-medium">Experience</h3><p className="mt-2">{profile.exp_min === null && profile.exp_max === null ? "No experience preference" : `${profile.exp_min ?? "0"} to ${profile.exp_max ?? "any"} years`}</p></section>
      <section className="rounded-xl border bg-white p-6"><h2 className="text-lg font-semibold">Skills</h2><h3 className="mt-4 font-medium">Required</h3><Items values={profile.skills.filter((item) => item.kind === "required").map((item) => item.name)} /><h3 className="mt-4 font-medium">Preferred</h3><Items values={profile.skills.filter((item) => item.kind === "preferred").map((item) => item.name)} /></section>
      <section className="rounded-xl border bg-white p-6"><h2 className="text-lg font-semibold">Work preferences</h2><h3 className="mt-4 font-medium">Employment</h3><Items values={profile.employment_types.length ? profile.employment_types.map(label) : ["Any employment type"]} /><h3 className="mt-4 font-medium">Work mode</h3><Items values={profile.work_modes.length ? profile.work_modes.map(label) : ["Any work mode"]} /><h3 className="mt-4 font-medium">Locations</h3><Items values={profile.locations.filter((item) => !item.excluded).map((item) => item.name)} /></section>
      <section className="rounded-xl border bg-white p-6"><h2 className="text-lg font-semibold">Exclusions</h2><h3 className="mt-4 font-medium">Keywords</h3><Items values={profile.exclusions.filter((item) => item.kind === "keyword").map((item) => item.term)} /><h3 className="mt-4 font-medium">Roles</h3><Items values={profile.exclusions.filter((item) => item.kind === "role").map((item) => item.term)} /><h3 className="mt-4 font-medium">Locations</h3><Items values={profile.locations.filter((item) => item.excluded).map((item) => item.name)} /></section>
    </div>
    <ProfileActions id={profile.id} name={profile.name} active={profile.active} />
  </>;
}
