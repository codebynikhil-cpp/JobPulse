import AppShell from "@/components/layout/AppShell";
import { requireUser } from "@/lib/session";
import { load } from "@/lib/product-api";
import type { Overview } from "@/types/product";
export const dynamic = "force-dynamic";
export default async function AuthenticatedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await requireUser();
  const dashboard = await load<Overview>("/api/dashboard");
  return (
    <AppShell
      email={user.email}
      unread={dashboard.stats.unread_notifications_count}
    >
      {children}
    </AppShell>
  );
}
