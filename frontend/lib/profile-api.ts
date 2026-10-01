import { Profile, ProfileInput } from "@/types/profile";

export async function changeProfile(id: string | null, method: "POST" | "PATCH" | "DELETE", data?: Partial<ProfileInput>): Promise<Profile | null> {
  const response = await fetch(`/api/profiles${id ? `/${id}` : ""}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  if (response.status === 401) {
    window.location.assign("/login");
    throw new Error("Your session expired. Please log in again.");
  }
  if (!response.ok) {
    const body = await response.json();
    const detail: unknown = body.detail;
    if (typeof detail === "string") throw new Error(detail);
    if (Array.isArray(detail)) {
      throw new Error(detail.map((item: { loc?: string[]; msg: string }) => [(item.loc || []).filter((part) => part !== "body").join("."), item.msg].filter(Boolean).join(": ")).join("; "));
    }
    throw new Error("Unable to save this change. Please retry.");
  }
  return response.status === 204 ? null : response.json();
}
