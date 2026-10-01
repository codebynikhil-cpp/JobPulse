import { requireUser } from "@/lib/session";
import AccountNav from "@/components/AccountNav";
import Logout from "@/components/Logout";
export default async function Account() {
  const user = await requireUser();
  return (
    <>
      <AccountNav />
      <h1>Account</h1>
      <p>{user.email}</p>
      <Logout />
    </>
  );
}
