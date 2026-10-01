import { NextRequest } from "next/server";
import { backendUrl } from "@/lib/backend";

export async function profileProxy(request: NextRequest, id?: string) {
  if (id && !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) {
    return Response.json({ detail: "Invalid profile ID" }, { status: 422 });
  }
  try {
    const response = await fetch(`${backendUrl()}/api/profiles${id ? `/${id}` : ""}${request.nextUrl.search}`, {
      method: request.method,
      headers: {
        "Content-Type": "application/json",
        cookie: request.headers.get("cookie") || "",
        origin: request.headers.get("origin") || "",
      },
      body: ["POST", "PATCH"].includes(request.method) ? await request.text() : undefined,
      cache: "no-store",
    });
    return new Response(response.status === 204 ? null : await response.text(), {
      status: response.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
    });
  } catch {
    return Response.json({ detail: "Profile service is unavailable. Please retry." }, { status: 502 });
  }
}
