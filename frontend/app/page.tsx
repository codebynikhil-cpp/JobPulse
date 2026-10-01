import Link from "next/link";
import { Activity } from "lucide-react";
export default function Home() {
  return (
    <main className="auth-page">
      <div className="brand">
        <Activity size={26} />
        JobPulse<span className="brand-dot">.</span>
      </div>
      <section className="auth-panel">
        <h1>Your search, in focus.</h1>
        <p>
          Monitor official company careers. Find opportunities that match your
          profiles. Keep your next move organized.
        </p>
        <div className="home-actions">
          <Link className="button button-primary" href="/signup">
            Create account
          </Link>
          <Link className="button button-secondary" href="/login">
            Log in
          </Link>
        </div>
      </section>
    </main>
  );
}
