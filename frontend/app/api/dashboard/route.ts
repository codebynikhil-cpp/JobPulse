import { NextRequest } from "next/server";
import { apiProxy } from "@/lib/api-proxy";

export function GET(request: NextRequest) {
  return apiProxy(request, "/api/dashboard");
}
