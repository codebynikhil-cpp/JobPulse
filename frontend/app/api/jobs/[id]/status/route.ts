import { NextRequest } from "next/server";
import { apiProxy } from "@/lib/api-proxy";

type Params = { params: Promise<{ id: string }> };

export async function GET(request: NextRequest, { params }: Params) {
  const { id } = await params;
  return apiProxy(request, `/api/jobs/${id}/status`);
}

export async function PATCH(request: NextRequest, { params }: Params) {
  const { id } = await params;
  return apiProxy(request, `/api/jobs/${id}/status`);
}

export async function POST(request: NextRequest, { params }: Params) {
  const { id } = await params;
  return apiProxy(request, `/api/jobs/${id}/status`);
}
