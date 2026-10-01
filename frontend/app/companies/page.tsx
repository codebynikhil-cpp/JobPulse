import { requireUser } from "@/lib/session";
import Workspace from "@/components/Workspace";
export const dynamic = "force-dynamic";
export default async function Page() {
  await requireUser();
  return <Workspace view="Companies" />;
}
