import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { backendUrl } from "@/lib/backend";
import Logout from "@/components/Logout";
export const dynamic = "force-dynamic";
export default async function Dashboard() {
  const response = await fetch(`${backendUrl()}/api/auth/me`, { headers: { cookie: (await cookies()).toString() }, cache: "no-store" });
  if (response.status === 401) redirect("/login");
  if (!response.ok) throw new Error("Unable to load account");
  const user: { email: string } = await response.json();
  return <><h1 className="text-3xl font-bold">Dashboard</h1><p className="mt-4">Signed in as {user.email}</p><div className="mt-8 rounded border bg-white p-6">Your account is ready. Job monitoring features will arrive in later phases.</div><Logout /></>;
}
