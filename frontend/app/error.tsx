"use client";
import { ErrorState } from "@/components/ui/feedback";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <ErrorState
      message="Unable to load this page. Please try again."
      retry={reset}
    />
  );
}
