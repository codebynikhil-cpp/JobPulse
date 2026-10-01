import Link from "next/link";
export default function Home() { return <><h1 className="text-3xl font-bold">Your next opportunity starts here.</h1><p className="my-5">Sign in to your JobPulse account.</p><div className="flex gap-5"><Link href="/login" className="underline">Log in</Link><Link href="/signup" className="underline">Create account</Link></div></>; }
