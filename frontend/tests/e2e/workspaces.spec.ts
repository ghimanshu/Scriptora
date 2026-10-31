import { expect, test } from "@playwright/test";
test("public entry points and author registration", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: /lasting impact/ }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: /Start your publishing journey/ })
    .click();
  await expect(page.getByLabel("Full name")).toBeVisible();
  await expect(page.getByLabel("Password")).toHaveAttribute("minlength", "12");
  let registrationPayload: unknown;
  await page.route("**/api/v1/auth/register", async (route) => {
    registrationPayload = route.request().postDataJSON();
    await route.fulfill({
      status: 201,
      json: { message: "Verification pending; check your email" },
    });
  });
  await page.getByLabel("Full name").fill("Test Author");
  await page.getByLabel("Email address").fill("author@example.com");
  await page.getByLabel("Password").fill("a sufficiently long test password");
  await page.getByRole("button", { name: /Create author account/ }).click();
  await expect(page.getByRole("status")).toContainText("Account created.");
  expect(registrationPayload).toEqual({
    display_name: "Test Author",
    email: "author@example.com",
    password: "a sufficiently long test password",
  });
});
test("author dashboard handles empty data, navigation, and small screens", async ({
  page,
}, testInfo) => {
  await page.route("**/api/v1/me", (route) =>
    route.fulfill({
      json: {
        id: "author",
        name: "Test Author",
        roles: ["AUTHOR"],
        email: "author@example.test",
      },
    }),
  );
  await page.route("**/api/v1/articles", (route) =>
    route.fulfill({ json: { items: [], next_cursor: null } }),
  );
  await page.goto("/author");
  await expect(
    page.getByRole("heading", { name: "Your ideas. Their next chapter." }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Your next chapter starts here" }),
  ).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("dashboard.png"),
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "Drafts", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Drafts", exact: true }),
  ).toHaveClass("selected");
});
test("an upstream failure is visible and can be retried", async ({ page }) => {
  await page.route("**/api/v1/me", (route) =>
    route.fulfill({ json: { id: "a", name: "Author", roles: ["AUTHOR"] } }),
  );
  await page.route("**/api/v1/articles", (route) =>
    route.fulfill({
      status: 502,
      json: {
        error: {
          code: "BACKEND_UNAVAILABLE",
          message: "Publishing service unavailable.",
        },
      },
    }),
  );
  await page.goto("/author");
  await expect(page.getByRole("alert").filter({ hasText: "Publishing service unavailable." })).toBeVisible();
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
  await page.route("**/api/v1/articles", route => route.fulfill({ json: { items: [], next_cursor: null } }));
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByRole("heading", { name: "Your next chapter starts here" })).toBeVisible();
});
test("BFF blocks arbitrary proxies and cross-origin login", async ({
  request,
}) => {
  expect((await request.get("/api/v1/arbitrary/proxy")).status()).toBe(404);
  expect(
    (
      await request.post("/api/v1/auth/login", {
        headers: { origin: "https://evil.example" },
        data: { email: "x", password: "x" },
      })
    ).status(),
  ).toBe(403);
});
