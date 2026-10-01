import { EmptyState } from "@/components/ui/primitives";
export default function MissingJob() {
  return (
    <EmptyState
      title="Job not found"
      description="This job is unavailable for your account."
      href="/jobs"
      action="Back to jobs"
    />
  );
}
