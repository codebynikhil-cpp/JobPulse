import type { Profile, ProfileInput } from "@/types/profile";
import { request } from "./client-api";
export function changeProfile(
  id: string | null,
  method: "POST" | "PATCH" | "DELETE",
  data?: Partial<ProfileInput>,
): Promise<Profile | null> {
  return request<Profile>(`/api/profiles${id ? `/${id}` : ""}`, method, data);
}
