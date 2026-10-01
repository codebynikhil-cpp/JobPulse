export const employmentTypes = ["full_time", "part_time", "contract", "internship", "temporary"] as const;
export const workModes = ["remote", "hybrid", "onsite"] as const;
export type EmploymentType = (typeof employmentTypes)[number];
export type WorkMode = (typeof workModes)[number];
export type Skill = { name: string; kind: "required" | "preferred" };
export type Location = { name: string; excluded: boolean };
export type Exclusion = { term: string; kind: "keyword" | "role" };
export type ProfileInput = {
  name: string;
  description: string;
  active: boolean;
  exp_min: number | null;
  exp_max: number | null;
  employment_types: EmploymentType[];
  work_modes: WorkMode[];
  roles: { name: string }[];
  skills: Skill[];
  locations: Location[];
  exclusions: Exclusion[];
};
export type Profile = Omit<ProfileInput, "exp_min" | "exp_max"> & {
  id: string;
  exp_min: string | null;
  exp_max: string | null;
  created_at: string;
  updated_at: string;
};
export function label(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
