import "server-only";
import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";
import type { NextRequest } from "next/server";
import { config } from "./config";
export function csrfToken(session: string) {
  const nonce = randomBytes(24).toString("hex");
  return `${nonce}.${createHmac("sha256", session).update(nonce).digest("hex")}`;
}
export function validCsrf(token: string, session: string) {
  const [nonce, signature] = token.split(".");
  if (!nonce || !signature || token.split(".").length !== 2) return false;
  const expected = createHmac("sha256", session).update(nonce).digest("hex");
  return (
    signature.length === expected.length &&
    timingSafeEqual(Buffer.from(signature), Buffer.from(expected))
  );
}
export function mutationAllowed(request: NextRequest, authenticated = true) {
  const c = config();
  if (request.headers.get("origin") !== c.origin) return false;
  if (!authenticated) return true;
  const session = request.cookies.get(c.names.refresh)?.value;
  const cookie = request.cookies.get(c.names.csrf)?.value;
  const header = request.headers.get("x-csrf-token");
  return (
    !!session && !!cookie && cookie === header && validCsrf(cookie, session)
  );
}
