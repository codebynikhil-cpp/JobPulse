import JobsPage from "@/components/jobs/JobsPage";
import type { Search } from "@/lib/product-api";
export default function Page({
  searchParams,
}: {
  searchParams: Promise<Search>;
}) {
  return <JobsPage view="Saved" searchParams={searchParams} />;
}
