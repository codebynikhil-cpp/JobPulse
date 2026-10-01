import { serverApi } from "./session";
import type { Profile } from "@/types/profile";
export async function load<T>(path: string): Promise<T> {
  const response = await serverApi(path);
  if (!response.ok) throw new Error("Unable to load this page. Please retry.");
  return response.json();
}
export async function allProfiles(): Promise<Profile[]> {
  const profiles: Profile[] = [];
  for (let offset = 0; ; offset += 100) {
    const batch = await load<Profile[]>(
      `/api/profiles?limit=100&offset=${offset}`,
    );
    profiles.push(...batch);
    if (batch.length < 100) return profiles;
  }
}
export type Search = Record<string, string | string[] | undefined>;
export function queryValues(search: Search) {
  return Object.fromEntries(
    Object.entries(search).flatMap(([key, value]) =>
      typeof value === "string" ? [[key, value]] : [],
    ),
  );
}
export function pageNumber(value?: string | string[]) {
  return typeof value === "string" && /^\d+$/.test(value)
    ? Math.min(100000, Math.max(1, Number(value)))
    : 1;
}
