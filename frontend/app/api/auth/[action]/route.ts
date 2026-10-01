import { NextRequest } from "next/server";
import { backendUrl } from "@/lib/backend";
export async function POST(request: NextRequest, { params }: { params: Promise<{ action: string }> }) {
  const { action } = await params;
  if (!["signup", "login", "logout"].includes(action)) return new Response(null, { status: 404 });
  const forwarded: Record<string, string> = {};
  // Enable only behind an ingress that overwrites untrusted forwarding headers.
  if (process.env.TRUST_FORWARDED_FOR === "true" && request.headers.get("x-forwarded-for")) {
    forwarded["x-forwarded-for"] = request.headers.get("x-forwarded-for")!;
  }
  const response = await fetch(`${backendUrl()}/api/auth/${action}`, { method: "POST", headers: { ...forwarded, "Content-Type": "application/json", cookie: request.headers.get("cookie") || "", origin: request.headers.get("origin") || "" }, body: await request.text(), cache: "no-store" });
  const headers = new Headers({ "Content-Type": "application/json" });
  for (const cookie of response.headers.getSetCookie()) headers.append("Set-Cookie", cookie);
  const retry = response.headers.get("retry-after"); if (retry) headers.set("Retry-After", retry);
  return new Response(response.status === 204 ? null : await response.text(), { status: response.status, headers });
}
