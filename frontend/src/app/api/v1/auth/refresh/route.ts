import { NextRequest } from "next/server";
import { auth } from "@/lib/server/auth";
export const runtime = "nodejs";
export function POST(request: NextRequest) {
  return auth(request, "refresh");
}
