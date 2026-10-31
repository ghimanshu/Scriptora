import { afterEach, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { auth } from "@/lib/server/auth";
import { csrfToken } from "@/lib/server/csrf";
afterEach(() => {
  vi.unstubAllGlobals();
});
it("keeps login tokens in HttpOnly cookies and out of JSON", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            access_token: "secret-access",
            refresh_token: "secret-refresh",
          }),
          { headers: { "content-type": "application/json" } },
        ),
    ),
  );
  const response = await auth(
    new NextRequest("http://localhost:3000/api/v1/auth/login", {
      method: "POST",
      headers: {
        origin: "http://localhost:3000",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        email: "author@example.test",
        password: "password",
      }),
    }),
    "login",
  );
  expect(await response.json()).toEqual({ authenticated: true });
  expect(response.cookies.get("publishing_access")?.value).toBe(
    "secret-access",
  );
  expect(response.headers.get("set-cookie")).toContain("HttpOnly");
  expect(response.headers.get("set-cookie")).toContain("SameSite=lax");
  expect(response.headers.get("cache-control")).toBe("no-store");
});
it("coalesces concurrent refresh requests to prevent rotating the same token twice", async () => {
  const refresh = "concurrent-test-refresh";
  const fetch = vi.fn(async () => {
    await new Promise((resolve) => setTimeout(resolve, 15));
    return new Response(
      JSON.stringify({
        access_token: "access-next",
        refresh_token: "refresh-next",
      }),
    );
  });
  vi.stubGlobal("fetch", fetch);
  const csrf = csrfToken(refresh);
  const request = () =>
    new NextRequest("http://localhost:3000/api/v1/auth/refresh", {
      method: "POST",
      headers: {
        origin: "http://localhost:3000",
        cookie: `publishing_refresh=${refresh}; publishing_csrf=${csrf}`,
        "x-csrf-token": csrf,
      },
    });
  const results = await Promise.all([
    auth(request(), "refresh"),
    auth(request(), "refresh"),
  ]);
  expect(fetch).toHaveBeenCalledTimes(1);
  results.forEach((response) => {
    expect(response.status).toBe(200);
    expect(response.cookies.get("publishing_refresh")?.value).toBe(
      "refresh-next",
    );
  });
});
