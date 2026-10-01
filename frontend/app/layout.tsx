import "./globals.css";
import Link from "next/link";
export const metadata = { title: "JobPulse" };
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="nav">
          <Link href="/dashboard" className="font-bold">
            JobPulse
          </Link>
        </header>
        <main className="page">{children}</main>
      </body>
    </html>
  );
}
