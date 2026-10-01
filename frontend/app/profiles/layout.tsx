import AccountNav from "@/components/AccountNav";
import { requireUser } from "@/lib/session";
export const dynamic = "force-dynamic";
export default async function ProfilesLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  await requireUser();
  return (
    <>
      <AccountNav />
      {children}
    </>
  );
}
