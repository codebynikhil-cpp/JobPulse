import "./globals.css";
import type { Metadata } from "next";
export const metadata: Metadata = {
  title: "JobPulse - Your search, in focus",
  description:
    "Monitor official company careers and discover jobs that match your profiles.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
