"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import TagEntry from "./TagEntry";
import { changeProfile } from "@/lib/profile-api";
import { employmentTypes, workModes, label, Profile, ProfileInput } from "@/types/profile";

export default function ProfileForm({ profile }: { profile?: Profile }) {
  const router = useRouter();
  const [name, setName] = useState(profile?.name || "");
  const [description, setDescription] = useState(profile?.description || "");
  const [active, setActive] = useState(profile?.active || false);
  const [minimum, setMinimum] = useState(profile?.exp_min ?? "");
  const [maximum, setMaximum] = useState(profile?.exp_max ?? "");
  const [employment, setEmployment] = useState(profile?.employment_types || []);
  const [modes, setModes] = useState(profile?.work_modes || []);
  const [roles, setRoles] = useState(profile?.roles.map((item) => item.name) || []);
  const [required, setRequired] = useState(profile?.skills.filter((item) => item.kind === "required").map((item) => item.name) || []);
  const [preferred, setPreferred] = useState(profile?.skills.filter((item) => item.kind === "preferred").map((item) => item.name) || []);
  const [locations, setLocations] = useState(profile?.locations.filter((item) => !item.excluded).map((item) => item.name) || []);
  const [excludedLocations, setExcludedLocations] = useState(profile?.locations.filter((item) => item.excluded).map((item) => item.name) || []);
  const [keywords, setKeywords] = useState(profile?.exclusions.filter((item) => item.kind === "keyword").map((item) => item.term) || []);
  const [excludedRoles, setExcludedRoles] = useState(profile?.exclusions.filter((item) => item.kind === "role").map((item) => item.term) || []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    const pending = Array.from(event.currentTarget.querySelectorAll<HTMLInputElement>("[data-entry-draft]")).find((input) => input.value.trim());
    if (pending) { setError("Use Add or Enter to keep your pending entry before saving."); pending.focus(); return; }
    if (minimum !== "" && maximum !== "" && Number(minimum) > Number(maximum)) {
      setError("Minimum experience must not exceed maximum experience."); return;
    }
    if (active && roles.length === 0) { setError("Add at least one role before activating."); return; }
    setBusy(true);
    const data: ProfileInput = {
      name, description, active,
      exp_min: minimum === "" ? null : Number(minimum), exp_max: maximum === "" ? null : Number(maximum),
      employment_types: employment, work_modes: modes,
      roles: roles.map((name) => ({ name })),
      skills: [...required.map((name) => ({ name, kind: "required" as const })), ...preferred.map((name) => ({ name, kind: "preferred" as const }))],
      locations: [...locations.map((name) => ({ name, excluded: false })), ...excludedLocations.map((name) => ({ name, excluded: true }))],
      exclusions: [...keywords.map((term) => ({ term, kind: "keyword" as const })), ...excludedRoles.map((term) => ({ term, kind: "role" as const }))],
    };
    try {
      const saved = await changeProfile(profile?.id || null, profile ? "PATCH" : "POST", data);
      router.push(`/profiles/${saved!.id}`); router.refresh();
    } catch (error) { setError(error instanceof Error ? error.message : "Unable to save profile."); }
    finally { setBusy(false); }
  }
  const panel = "space-y-5 rounded-xl border border-slate-200 bg-white p-6";
  return <form onSubmit={submit} className="space-y-6">
    <fieldset disabled={busy} className="space-y-6 disabled:opacity-60">
      <section className={panel} aria-labelledby="basics">
        <h2 id="basics" className="text-lg font-semibold">Profile basics</h2>
        <label className="block font-medium">Name<input value={name} onChange={(event) => setName(event.target.value)} required maxLength={100} placeholder="Software Engineer - Early Career" /></label>
        <label className="block font-medium">Description <span className="font-normal text-slate-500">(optional)</span><textarea value={description} onChange={(event) => setDescription(event.target.value)} maxLength={2000} rows={3} className="mt-1 w-full rounded border border-slate-400 p-3" placeholder="What are you looking for?" /></label>
        <label className="flex items-center gap-3"><input type="checkbox" className="!w-4" checked={active} onChange={(event) => setActive(event.target.checked)} />Active profile</label>
        <p className="text-sm text-slate-600">Active profiles are ready for future monitoring. Add at least one target role to activate.</p>
      </section>
      <section className={panel} aria-labelledby="roles"><h2 id="roles" className="text-lg font-semibold">Roles and experience</h2>
        <TagEntry label="Target roles" hint="Add each role separately, for example Software Engineer or Backend Developer." values={roles} onChange={setRoles} />
        <div className="grid gap-4 sm:grid-cols-2"><label>Minimum experience (years)<input type="number" min="0" max="60" step="0.1" value={minimum} onChange={(event) => setMinimum(event.target.value)} placeholder="No minimum" /></label><label>Maximum experience (years)<input type="number" min="0" max="60" step="0.1" value={maximum} onChange={(event) => setMaximum(event.target.value)} placeholder="No maximum" /></label></div>
        <p className="text-sm text-slate-600">Leave either bound blank if you have no preference.</p>
      </section>
      <section className={panel} aria-labelledby="skills"><h2 id="skills" className="text-lg font-semibold">Skills</h2>
        <TagEntry label="Required skills" hint="Must-have skills. A skill belongs in only one list." values={required} onChange={setRequired} />
        <TagEntry label="Preferred skills" hint="Nice-to-have skills, separate from requirements." values={preferred} onChange={setPreferred} />
      </section>
      <section className={panel} aria-labelledby="preferences"><h2 id="preferences" className="text-lg font-semibold">Where and how you work</h2>
        <fieldset><legend className="mb-2 font-medium">Employment types</legend><div className="flex flex-wrap gap-4">{employmentTypes.map((value) => <label key={value} className="flex items-center gap-2"><input type="checkbox" className="!w-4" checked={employment.includes(value)} onChange={(event) => setEmployment(event.target.checked ? [...employment, value] : employment.filter((item) => item !== value))} />{label(value)}</label>)}</div></fieldset>
        <fieldset><legend className="mb-2 font-medium">Work modes</legend><div className="flex flex-wrap gap-4">{workModes.map((value) => <label key={value} className="flex items-center gap-2"><input type="checkbox" className="!w-4" checked={modes.includes(value)} onChange={(event) => setModes(event.target.checked ? [...modes, value] : modes.filter((item) => item !== value))} />{label(value)}</label>)}</div></fieldset>
        <p className="text-sm text-slate-600">No selection means any employment type or work mode. Remote jobs can still have geographic restrictions.</p>
        <TagEntry label="Preferred locations" hint="Add cities, regions or countries separately." values={locations} onChange={setLocations} />
        <TagEntry label="Excluded locations" hint="Locations you want to avoid; do not also add them as preferred." values={excludedLocations} onChange={setExcludedLocations} />
      </section>
      <section className={panel} aria-labelledby="exclusions"><h2 id="exclusions" className="text-lg font-semibold">Exclusions</h2>
        <TagEntry label="Excluded keywords" hint="Terms to avoid, for example Manager. Do not exclude an exact target role." values={keywords} onChange={setKeywords} />
        <TagEntry label="Excluded roles" hint="Unwanted role names, separate from your target roles." values={excludedRoles} onChange={setExcludedRoles} />
      </section>
    </fieldset>
    {error && <div role="alert" className="rounded border border-red-200 bg-red-50 p-4 text-red-800">{error}</div>}
    <div className="flex items-center gap-5"><button disabled={busy} className="rounded bg-blue-700 px-6 py-3 font-medium text-white disabled:opacity-50">{busy ? "Saving..." : profile ? "Save changes" : "Create profile"}</button><Link href={profile ? `/profiles/${profile.id}` : "/profiles"} className="underline">Cancel</Link></div>
  </form>;
}
