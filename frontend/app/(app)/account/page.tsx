import { requireUser } from "@/lib/session";
import { PageHeader } from "@/components/ui/primitives";
import Logout from "@/components/Logout";
export default async function Account() {
  const user = await requireUser();
  return (
    <>
      <PageHeader
        title="Account"
        description="Your personal JobPulse workspace."
      />
      <section className="account-section">
        <h2>Account details</h2>
        <dl>
          <dt>Email address</dt>
          <dd>{user.email}</dd>
        </dl>
      </section>
      <section className="account-section">
        <h2>Session</h2>
        <p className="muted">Log out of this session on this device.</p>
        <Logout />
      </section>
    </>
  );
}
