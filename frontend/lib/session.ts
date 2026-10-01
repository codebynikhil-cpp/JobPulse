import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { backendUrl } from "./backend";

export async function serverApi(path: string): Promise<Response> {
  const response = await fetch(`${backendUrl()}${path}`, {
    headers: { cookie: (await cookies()).toString() },
    cache: "no-store",
  });
  if (response.status === 401) redirect("/login");
  return response;
}

export async function requireUser(): Promise<{ id: string; email: string }> {
  const response = await serverApi("/api/auth/me");
  if (!response.ok) throw new Error("Unable to load account");
  return response.json();
}
