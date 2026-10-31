import "server-only";
import { NextRequest, NextResponse } from "next/server";
import { createHash, randomUUID } from "node:crypto";
import { backend, failure, safeResponse } from "./backend-client";
import { config } from "./config";
import { mutationAllowed } from "./csrf";
import { clearSession, setSession, type Tokens } from "./session";
// A refresh token is consumed once per process. Multi-replica deployments need sticky
// session routing or a shared coordinator before enabling concurrent refresh traffic.
const refreshes = new Map<string, Promise<Tokens | null>>();
async function rotate(refresh: string): Promise<Tokens | null> {
  const key = createHash("sha256").update(refresh).digest("hex");
  const pending = refreshes.get(key);
  if (pending) return pending;
  if (refreshes.size >= 1000) throw new Error("Refresh capacity exceeded");
  const task = (async () => {
    const result = await backend("auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
      signal: AbortSignal.timeout(config().timeout),
    });
    if (result.status >= 500) throw new Error("Refresh service unavailable");
    if (!result.ok) return null;
    return (await result.json()) as Tokens;
  })();
  refreshes.set(key, task);
  const expiry = setTimeout(() => refreshes.delete(key), 10000);
  expiry.unref();
  return task;
}
export async function auth(
  request: NextRequest,
  action: "login" | "refresh" | "logout",
) {
  if (!mutationAllowed(request, action !== "login"))
    return failure(
      403,
      "CSRF_FAILED",
      "Security validation failed. Reload the page.",
    );
  const c = config();
  try {
    if (action === "logout") {
      const refresh = request.cookies.get(c.names.refresh)?.value;
      const access = request.cookies.get(c.names.access)?.value;
      const result = await backend("auth/logout", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(access ? { Authorization: `Bearer ${access}` } : {}),
        },
        body: JSON.stringify({ refresh_token: refresh }),
        signal: AbortSignal.timeout(c.timeout),
      });
      if (!result.ok && result.status !== 401)
        return safeResponse(result, randomUUID());
      const response = new NextResponse(null, {
        status: 204,
        headers: { "Cache-Control": "no-store" },
      });
      clearSession(response);
      return response;
    }
    let tokens: Tokens | null;
    if (action === "refresh") {
      const refresh = request.cookies.get(c.names.refresh)?.value;
      tokens = refresh ? await rotate(refresh) : null;
    } else {
      if (Number(request.headers.get("content-length") || 0) > 16384)
        return failure(413, "BODY_TOO_LARGE", "Request too large.");
      const reader = request.body?.getReader();
      if (!reader)
        return failure(422, "INVALID_LOGIN", "Enter your email and password.");
      let raw = "";
      const decoder = new TextDecoder();
      while (true) {
        const part = await reader.read();
        if (part.done) break;
        raw += decoder.decode(part.value, { stream: true });
        if (raw.length > 16384) {
          await reader.cancel();
          return failure(413, "BODY_TOO_LARGE", "Request too large.");
        }
      }
      const data = JSON.parse(raw);
      if (typeof data.email !== "string" || typeof data.password !== "string")
        return failure(422, "INVALID_LOGIN", "Enter your email and password.");
      const result = await backend("auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: data.email, password: data.password }),
        signal: AbortSignal.timeout(c.timeout),
      });
      if (!result.ok) return safeResponse(result, randomUUID());
      tokens = await result.json();
    }
    if (!tokens?.access_token || !tokens?.refresh_token) {
      const response = failure(
        401,
        "SESSION_EXPIRED",
        "Your session expired. Sign in again.",
      );
      clearSession(response);
      return response;
    }
    const response = NextResponse.json(
      { authenticated: true },
      { headers: { "Cache-Control": "no-store" } },
    );
    setSession(response, tokens);
    return response;
  } catch {
    return failure(
      502,
      "BACKEND_UNAVAILABLE",
      "The sign-in service is unavailable. Please try again.",
    );
  }
}
