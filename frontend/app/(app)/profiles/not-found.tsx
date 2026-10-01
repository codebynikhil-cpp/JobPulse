import Link from "next/link";
export default function MissingProfile() {
  return (
    <div>
      <h1 className="text-2xl font-bold">Profile not found</h1>
      <p className="my-4">This profile is unavailable for your account.</p>
      <Link prefetch={false} href="/profiles" className="underline">
        Back to profiles
      </Link>
    </div>
  );
}
