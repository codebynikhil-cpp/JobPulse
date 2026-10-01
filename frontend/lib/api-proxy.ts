/**
 * Generic backend API proxy helper for any path.
 * Forwards cookies and origin, passes through status and body.
 */
import { NextRequest } from "next/server";
import { backendUrl } from "@/lib/backend";

export async function apiProxy(
  request: NextRequest,
  backendPath: string,
  options?: { body?: string | null }
): Promise<Response> {
  try {
    const hasBody = ["POST", "PUT", "PATCH"].includes(request.method);
    const bodyText = hasBody
      ? (options?.body !== undefined ? options.body : await request.text())
      : undefined;

    const res = await fetch(`${backendUrl()}${backendPath}${request.nextUrl.search}`, {
      method: request.method,
      headers: {
        "Content-Type": "application/json",
        cookie: request.headers.get("cookie") || "",
        origin: request.headers.get("origin") || "",
      },
      body: bodyText ?? undefined,
      cache: "no-store",
    });

    const text = res.status === 204 ? "" : await res.text();
    return new Response(text || null, {
      status: res.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
    });
  } catch {
    return Response.json({ detail: "Service unavailable" }, { status: 502 });
  }
}
