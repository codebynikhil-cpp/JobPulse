import { NextRequest } from "next/server";
import { profileProxy } from "@/lib/profile-proxy";
export function GET(request: NextRequest) { return profileProxy(request); }
export function POST(request: NextRequest) { return profileProxy(request); }
