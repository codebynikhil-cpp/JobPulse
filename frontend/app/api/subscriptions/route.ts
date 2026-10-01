import { NextRequest } from "next/server";
import { apiProxy } from "@/lib/api-proxy";

export function GET(request: NextRequest) {
  return apiProxy(request, "/api/subscriptions");
}

export function POST(request: NextRequest) {
  return apiProxy(request, "/api/subscriptions/toggle");
}
