import Link from "next/link";
import { requireUser } from "@/lib/session";
import Logout from "@/components/Logout";
export const dynamic = "force-dynamic";
export default async function Dashboard() {
  const user = await requireUser();
  return <><h1 className="text-3xl font-bold">Dashboard</h1><p className="mt-4">Signed in as {user.email}</p><div className="mt-8 rounded border bg-white p-6">Your account is ready. Set up the roles, skills and preferences for your search.<Link href="/profiles" className="mt-4 block font-medium text-blue-700 underline">Manage profiles</Link></div><Logout /></>;
}
