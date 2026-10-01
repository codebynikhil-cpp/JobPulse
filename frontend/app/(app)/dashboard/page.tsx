import Dashboard from "@/components/dashboard/Dashboard";
import { load } from "@/lib/product-api";
import type { Overview } from "@/types/product";
export default async function Page() {
  return <Dashboard data={await load<Overview>("/api/dashboard")} />;
}
