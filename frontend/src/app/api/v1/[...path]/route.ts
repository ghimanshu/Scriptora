import { NextRequest } from "next/server";
import { forward } from "@/lib/server/backend-client";
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
async function handle(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  return forward(request, (await context.params).path.join("/"));
}
export {
  handle as GET,
  handle as POST,
  handle as PUT,
  handle as PATCH,
  handle as DELETE,
};
