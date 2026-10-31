import { describe, expect, it } from "vitest";
// Opt-in read-only checks against an actual disposable backend environment.
describe.skipIf(!process.env.TEST_BACKEND_URL)("real backend contract", () => {
  it("is ready and exposes the required API contract", async () => {
    const origin = new URL(process.env.TEST_BACKEND_URL!);
    expect((await fetch(new URL("/api/v1/health/ready", origin))).ok).toBe(
      true,
    );
    const schema = await (await fetch(new URL("/openapi.json", origin))).json();
    expect(schema.paths["/api/v1/articles"].post).toBeDefined();
    expect(
      schema.paths["/api/v1/assignments/{id}/review"] ||
        Object.keys(schema.paths).find((path) =>
          /^\/api\/v1\/assignments\/\{.+\}\/review$/.test(path),
        ),
    ).toBeTruthy();
    expect((await fetch(new URL("/api/v1/me", origin))).status).toBe(401);
  });
});
