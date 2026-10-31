import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { allowed, publicPath } from "@/lib/server/route-allowlist";
import { csrfToken, validCsrf, mutationAllowed } from "@/lib/server/csrf";
import { forward, safeResponse } from "@/lib/server/backend-client";
import { config } from "@/lib/server/config";
const id = "123e4567-e89b-42d3-a456-426614174000";
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});
describe("BFF trust boundaries", () => {
  it("allows documented commands and rejects arbitrary destinations and generic status updates", () => {
    expect(allowed("POST", `articles/${id}/claim`)).toBe(true);
    for (const path of [
      "https://evil.test",
      "../auth/login",
      "admin/users/anything",
      `articles/${id}/status`,
      "public/articles/x/../../me",
      "auth/login",
    ])
      expect(allowed("POST", path)).toBe(false);
    expect(allowed("GET", `files/${id}/download`)).toBe(true);
    expect(allowed("DELETE", `articles/${id}`)).toBe(false);
    expect(publicPath(`articles/${id}`)).toBe(false);
  });
  it("binds CSRF to the refresh session and exact browser origin", () => {
    const token = csrfToken("session-A");
    expect(validCsrf(token, "session-A")).toBe(true);
    expect(validCsrf(token, "session-B")).toBe(false);
    const headers = {
      origin: "http://localhost:3000",
      cookie: `publishing_refresh=session-A; publishing_csrf=${token}`,
      "x-csrf-token": token,
    };
    expect(
      mutationAllowed(
        new NextRequest("http://localhost:3000/api/v1/articles", {
          method: "POST",
          headers,
        }),
      ),
    ).toBe(true);
    expect(
      mutationAllowed(
        new NextRequest("http://localhost:3000/api/v1/articles", {
          method: "POST",
          headers: { ...headers, origin: "https://evil.test" },
        }),
      ),
    ).toBe(false);
  });
  it("rejects missing production cookie security settings", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("COOKIE_SECURE", "false");
    expect(() => config()).toThrow("secure cookies");
  });
  it("rejects private requests before contacting the backend", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const response = await forward(
      new NextRequest("http://localhost:3000/api/v1/me"),
      "me",
    );
    expect(response.status).toBe(401);
    expect(fetch).not.toHaveBeenCalled();
  });
  it("preserves status and safe codes without leaking internal messages or cookies", async () => {
    const upstream = new Response(
      JSON.stringify({
        error: {
          code: "ASSIGNMENT_EXPIRED",
          message: "postgres password secret",
        },
      }),
      {
        status: 409,
        headers: { "set-cookie": "secret=abc", "x-request-id": "trace-123" },
      },
    );
    const response = await safeResponse(upstream, "fallback");
    expect(response.status).toBe(409);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(response.headers.get("set-cookie")).toBeNull();
    const data = await response.json();
    expect(data.error.code).toBe("ASSIGNMENT_EXPIRED");
    expect(data.error.request_id).toBe("trace-123");
    expect(JSON.stringify(data)).not.toContain("password");
  });
  it("does not relay backend redirects", async () => {
    const response = await safeResponse(
      new Response(null, {
        status: 302,
        headers: { location: "https://evil.test" },
      }),
      "trace",
    );
    expect(response.status).toBe(502);
    expect(response.headers.get("location")).toBeNull();
  });
  it("streams uploads to a fixed destination and filters incoming credentials", async () => {
    const fetch = vi.fn(async (_url: string, init: RequestInit) => {
      expect(init.redirect).toBe("manual");
      expect(new Headers(init.headers).get("cookie")).toBeNull();
      expect(new Headers(init.headers).get("authorization")).toBe(
        "Bearer access",
      );
      return new Response(JSON.stringify({ id }), {
        status: 201,
        headers: { "content-type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetch);
    const token = csrfToken("refresh");
    const response = await forward(
      new NextRequest("http://localhost:3000/api/v1/files", {
        method: "POST",
        headers: {
          origin: "http://localhost:3000",
          cookie: `publishing_access=access; publishing_refresh=refresh; publishing_csrf=${token}`,
          "x-csrf-token": token,
          "content-type": "multipart/form-data; boundary=x",
        },
        body: "--x--",
      }),
      "files",
    );
    expect(response.status).toBe(201);
    await response.text();
    expect(fetch.mock.calls[0][0]).toBe("http://127.0.0.1:8000/api/v1/files");
  });
});
