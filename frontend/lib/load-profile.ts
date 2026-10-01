import "server-only";
import { notFound } from "next/navigation";
import { serverApi } from "./session";
import { Profile } from "@/types/profile";
export async function loadProfile(id: string): Promise<Profile> {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) notFound();
  const response = await serverApi(`/api/profiles/${id}`);
  if (response.status === 404) notFound();
  if (!response.ok) throw new Error("Unable to load profile");
  return response.json();
}
