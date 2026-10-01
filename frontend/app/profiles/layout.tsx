import Link from "next/link";
import { requireUser } from "@/lib/session";
export const dynamic = "force-dynamic";
export default async function ProfilesLayout({ children }: { children: React.ReactNode }) {
  await requireUser();
  return <><nav aria-label="Account navigation" className="mb-8 flex gap-5 text-sm"><Link href="/dashboard" className="underline">Dashboard</Link><Link href="/profiles" className="underline">Profiles</Link></nav>{children}</>;
}
