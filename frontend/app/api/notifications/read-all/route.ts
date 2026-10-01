import { NextRequest } from "next/server";
import { apiProxy } from "@/lib/api-proxy";

export async function PATCH(request: NextRequest) {
  return apiProxy(request, "/api/notifications/read-all");
}

export async function POST(request: NextRequest) {
  return apiProxy(request, "/api/notifications/read-all");
}
