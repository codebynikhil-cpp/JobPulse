import "./globals.css";
import { Outfit } from "next/font/google";
const outfit = Outfit({ subsets: ["latin"], weight: ["400", "500", "700", "900"], variable: "--font-outfit", display: "swap" });
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
      <body className={outfit.variable}>{children}</body>
    </html>
  );
}
