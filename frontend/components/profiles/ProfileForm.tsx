"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import TagEntry from "./TagEntry";
import { Button } from "@/components/ui/primitives";
import { ErrorState, useToast } from "@/components/ui/feedback";
import FormSection from "./FormSection";
import { changeProfile } from "@/lib/profile-api";
import {
  employmentTypes,
  workModes,
  label,
  Profile,
  ProfileInput,
} from "@/types/profile";

export default function ProfileForm({ profile }: { profile?: Profile }) {
  const router = useRouter();
  const toast = useToast();
  const [name, setName] = useState(profile?.name || "");
  const [description, setDescription] = useState(profile?.description || "");
  const [active, setActive] = useState(profile?.active || false);
  const [minimum, setMinimum] = useState(profile?.exp_min ?? "");
  const [maximum, setMaximum] = useState(profile?.exp_max ?? "");
  const [employment, setEmployment] = useState(profile?.employment_types || []);
  const [modes, setModes] = useState(profile?.work_modes || []);
  const [roles, setRoles] = useState(
    profile?.roles.map((item) => item.name) || [],
  );
  const [required, setRequired] = useState(
    profile?.skills
      .filter((item) => item.kind === "required")
      .map((item) => item.name) || [],
  );
  const [preferred, setPreferred] = useState(
    profile?.skills
      .filter((item) => item.kind === "preferred")
      .map((item) => item.name) || [],
  );
  const [locations, setLocations] = useState(
    profile?.locations
      .filter((item) => !item.excluded)
      .map((item) => item.name) || [],
  );
  const [excludedLocations, setExcludedLocations] = useState(
    profile?.locations
      .filter((item) => item.excluded)
      .map((item) => item.name) || [],
  );
  const [keywords, setKeywords] = useState(
    profile?.exclusions
      .filter((item) => item.kind === "keyword")
      .map((item) => item.term) || [],
  );
  const [excludedRoles, setExcludedRoles] = useState(
    profile?.exclusions
      .filter((item) => item.kind === "role")
      .map((item) => item.term) || [],
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const pending = Array.from(
      event.currentTarget.querySelectorAll<HTMLInputElement>(
        "[data-entry-draft]",
      ),
    ).find((input) => input.value.trim());
    if (pending) {
      setError("Use Add or Enter to keep your pending entry before saving.");
      pending.focus();
      return;
    }
    if (minimum !== "" && maximum !== "" && Number(minimum) > Number(maximum)) {
      setError("Minimum experience must not exceed maximum experience.");
      return;
    }
    if (active && roles.length === 0) {
      setError("Add at least one role before activating.");
      return;
    }
    setBusy(true);
    const data: ProfileInput = {
      name,
      description,
      active,
      exp_min: minimum === "" ? null : Number(minimum),
      exp_max: maximum === "" ? null : Number(maximum),
      employment_types: employment,
      work_modes: modes,
      roles: roles.map((name) => ({ name })),
      skills: [
        ...required.map((name) => ({ name, kind: "required" as const })),
        ...preferred.map((name) => ({ name, kind: "preferred" as const })),
      ],
      locations: [
        ...locations.map((name) => ({ name, excluded: false })),
        ...excludedLocations.map((name) => ({ name, excluded: true })),
      ],
      exclusions: [
        ...keywords.map((term) => ({ term, kind: "keyword" as const })),
        ...excludedRoles.map((term) => ({ term, kind: "role" as const })),
      ],
    };
    try {
      const saved = await changeProfile(
        profile?.id || null,
        profile ? "PATCH" : "POST",
        data,
      );
      if (!saved)
        throw new Error("The profile could not be saved. Please retry.");
      toast(profile ? "Profile updated." : "Profile created.");
      router.push(`/profiles/${saved.id}`);
      router.refresh();
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "Unable to save profile.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="profile-form">
      <fieldset disabled={busy}>
        <FormSection
          id="basics"
          title="Profile basics"
          description="Give this search a clear purpose."
        >
          <label>
            Name
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
              maxLength={100}
              placeholder="Software Engineer - Early Career"
            />
          </label>
          <label>
            Description <span className="muted">(optional)</span>
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              maxLength={2000}
              rows={3}
              placeholder="What are you looking for?"
            />
          </label>
          <div>
            <label className="checkbox-field">
              <input
                type="checkbox"
                checked={active}
                onChange={(event) => setActive(event.target.checked)}
              />
              Active profile
            </label>
            <p className="field-hint">
              Active profiles match jobs from your monitored companies. Add at
              least one role to activate.
            </p>
          </div>
        </FormSection>
        <FormSection
          id="roles"
          title="Target roles"
          description="The titles and roles you want to discover."
        >
          <TagEntry
            label="Target roles"
            hint="Add each role separately, for example Software Engineer or Backend Developer."
            values={roles}
            onChange={setRoles}
          />
        </FormSection>
        <FormSection
          id="skills"
          title="Skills"
          description="Separate must-have skills from preferences."
        >
          <TagEntry
            label="Required skills"
            hint="A skill belongs in only one list."
            values={required}
            onChange={setRequired}
          />
          <TagEntry
            label="Preferred skills"
            hint="Skills you would like to use in your next role."
            values={preferred}
            onChange={setPreferred}
          />
        </FormSection>
        <FormSection
          id="experience"
          title="Experience"
          description="Set your preferred range in years."
        >
          <div className="form-grid">
            <label>
              Minimum experience (years)
              <input
                type="number"
                min="0"
                max="60"
                step="0.1"
                value={minimum}
                onChange={(event) => setMinimum(event.target.value)}
                placeholder="No minimum"
              />
            </label>
            <label>
              Maximum experience (years)
              <input
                type="number"
                min="0"
                max="60"
                step="0.1"
                value={maximum}
                onChange={(event) => setMaximum(event.target.value)}
                placeholder="No maximum"
              />
            </label>
          </div>
          <p className="field-hint">
            Leave either bound blank if you have no preference.
          </p>
        </FormSection>
        <FormSection
          id="locations"
          title="Locations"
          description="Where you would like to work."
        >
          <TagEntry
            label="Preferred locations"
            hint="Cities, regions, or countries. Leave empty for any location."
            values={locations}
            onChange={setLocations}
          />
          <TagEntry
            label="Excluded locations"
            hint="Locations you want to avoid."
            values={excludedLocations}
            onChange={setExcludedLocations}
          />
        </FormSection>
        <FormSection
          id="employment"
          title="Employment"
          description="Choose contract types and work arrangements."
        >
          <div>
            <h3>Employment types</h3>
            <div className="checkbox-options">
              {employmentTypes.map((type) => (
                <label key={type}>
                  <input
                    type="checkbox"
                    checked={employment.includes(type)}
                    onChange={(e) =>
                      setEmployment(
                        e.target.checked
                          ? [...employment, type]
                          : employment.filter((item) => item !== type),
                      )
                    }
                  />
                  {label(type)}
                </label>
              ))}
            </div>
          </div>
          <div>
            <h3>Work modes</h3>
            <div className="checkbox-options">
              {workModes.map((mode) => (
                <label key={mode}>
                  <input
                    type="checkbox"
                    checked={modes.includes(mode)}
                    onChange={(e) =>
                      setModes(
                        e.target.checked
                          ? [...modes, mode]
                          : modes.filter((item) => item !== mode),
                      )
                    }
                  />
                  {label(mode)}
                </label>
              ))}
            </div>
          </div>
          <p className="field-hint">
            Leave all unchecked to keep your options open.
          </p>
        </FormSection>
        <FormSection
          id="exclusions"
          title="Exclusions"
          description="Keep unsuitable roles out of your search."
        >
          <TagEntry
            label="Excluded keywords"
            hint="Terms to avoid in job titles, such as Senior or Principal."
            values={keywords}
            onChange={setKeywords}
          />
          <TagEntry
            label="Excluded roles"
            hint="Roles you do not want to match."
            values={excludedRoles}
            onChange={setExcludedRoles}
          />
        </FormSection>
      </fieldset>
      {error && <ErrorState message={error} />}
      <div className="form-actions">
        <Button variant="primary" disabled={busy}>
          {busy ? "Saving..." : profile ? "Save changes" : "Create profile"}
        </Button>
        <Link
          prefetch={false}
          href={profile ? `/profiles/${profile.id}` : "/profiles"}
        >
          Cancel
        </Link>
      </div>
    </form>
  );
}
