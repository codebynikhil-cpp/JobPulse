import { NextRequest } from "next/server";
import { profileProxy } from "@/lib/profile-proxy";
type Context = { params: Promise<{ id: string }> };
async function proxy(request: NextRequest, context: Context) {
  return profileProxy(request, (await context.params).id);
}
export const GET = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
