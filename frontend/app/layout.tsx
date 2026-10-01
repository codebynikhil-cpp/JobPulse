import "./globals.css";
import Link from "next/link";
export const metadata = { title: "JobPulse" };
export default function Layout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body><header className="border-b bg-white px-8 py-5"><Link href="/" className="text-xl font-bold">JobPulse</Link></header><main className="mx-auto max-w-3xl p-8">{children}</main></body></html>;
}
