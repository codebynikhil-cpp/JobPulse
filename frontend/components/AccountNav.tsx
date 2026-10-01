import Link from "next/link";
export default function AccountNav() {
  return (
    <nav className="workspace-nav" aria-label="Account navigation">
      {[
        "Dashboard",
        "Jobs",
        "Saved",
        "Applied",
        "Notifications",
        "Profiles",
        "Companies",
        "Account",
      ].map((v) => (
        <Link key={v} href={`/${v.toLowerCase()}`}>
          {v}
        </Link>
      ))}
    </nav>
  );
}
