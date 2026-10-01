"use client";
export default function ErrorPage({ reset }: { reset: () => void }) { return <div role="alert"><p>Unable to load this page.</p><button onClick={reset} className="mt-4 underline">Try again</button></div>; }
