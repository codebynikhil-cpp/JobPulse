import { requireUser } from "@/lib/session";
import Workspace from "@/components/Workspace";
export const dynamic = "force-dynamic";
export default async function Page() {
  const user = await requireUser();
  return (
    <>
      <p className="text-muted">Signed in as {user.email}</p>
      <Workspace view="Dashboard" />
    </>
  );
}
