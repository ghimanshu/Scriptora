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
    role: "AUTHOR",
    display_name: "Test Author",
    email: "author@example.com",
    password: "a sufficiently long test password",
  });
});

test("reviewer registration submits an application requiring admin approval", async ({ page }) => {
  let payload: unknown;
  await page.route("**/api/v1/auth/register", async (route) => {
    payload = route.request().postDataJSON();
    await route.fulfill({ status: 201, json: { message: "Verification pending" } });
  });
  await page.goto("/register");
  await page.getByLabel("Register as").selectOption("REVIEWER");
  await page.getByLabel("Full name").fill("Test Reviewer");
  await page.getByLabel("Email address").fill("reviewer@example.com");
  await page.getByLabel("Password").fill("a sufficiently long test password");
  await page.getByRole("button", { name: /Apply as reviewer/ }).click();
  await expect(page.getByRole("status")).toContainText("an admin approves or rejects your application");
  expect(payload).toEqual({ role: "REVIEWER", display_name: "Test Reviewer", email: "reviewer@example.com", password: "a sufficiently long test password" });
});

test("pending reviewers see approval instructions when signing in", async ({ page }) => {
  await page.route("**/api/v1/auth/login", (route) => route.fulfill({
    status: 403, json: { error: { code: "REVIEWER_APPROVAL_PENDING" } },
  }));
  await page.goto("/login");
  await page.getByLabel("Email address").fill("reviewer@example.com");
  await page.getByLabel("Password", { exact: true }).fill("a sufficiently long test password");
  await page.getByRole("button", { name: /Sign in/ }).click();
  await expect(page.getByRole("alert").filter({ hasText: "awaiting admin approval" })).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});

test("admin approves an unverified reviewer application", async ({ page }) => {
  const reviewer = { id: "reviewer", name: "Test Reviewer", email: "reviewer@example.com", email_verified: false, active: true };
  let approved = false;
  await page.route("**/api/v1/me", (route) => route.fulfill({ json: { id: "admin", name: "Admin", roles: ["ADMIN"] } }));
  await page.route("**/api/v1/admin/users?*", (route) => route.fulfill({ json: { items: [{ ...reviewer, roles: ["REVIEWER"] }] } }));
  await page.route("**/api/v1/admin/reviewers", (route) => route.fulfill({ json: { items: approved ? [] : [reviewer] } }));
  await page.route("**/api/v1/admin/reviewers/reviewer/approve", async (route) => {
    expect(route.request().postDataJSON()).toEqual({ reason: "Qualifications verified" });
    approved = true;
    await route.fulfill({ json: { approved: true } });
  });
  page.on("dialog", (dialog) => dialog.accept("Qualifications verified"));
  await page.goto("/admin/users");
  await page.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Reviewer approval recorded" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve", exact: true })).toHaveCount(0);
  expect(approved).toBe(true);
});

test("admin rejects a reviewer application and it leaves the queue", async ({ page }) => {
  const reviewer = { id: "reviewer", name: "Test Reviewer", email: "reviewer@example.com", email_verified: false, active: true };
  let rejected = false;
  await page.route("**/api/v1/me", (route) => route.fulfill({ json: { id: "admin", name: "Admin", roles: ["ADMIN"] } }));
  await page.route("**/api/v1/admin/users?*", (route) => route.fulfill({ json: { items: [] } }));
  await page.route("**/api/v1/admin/reviewers", (route) => route.fulfill({ json: { items: rejected ? [] : [reviewer] } }));
  await page.route("**/api/v1/admin/reviewers/reviewer/reject", async (route) => {
    expect(route.request().postDataJSON()).toEqual({ reason: "Insufficient relevant experience" });
    rejected = true;
    await route.fulfill({ json: { approved: false, rejected: true } });
  });
  page.on("dialog", (dialog) => dialog.accept("Insufficient relevant experience"));
  await page.goto("/admin/users");
  await page.getByRole("button", { name: "Reject", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Decision email queued" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Reject", exact: true })).toHaveCount(0);
  expect(rejected).toBe(true);
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
test("author dashboard handles article records without a title", async ({
  page,
}) => {
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
    route.fulfill({
      json: {
        items: [
          {
            id: "article",
            status: "DRAFT",
            created_at: "2026-10-31T00:00:00Z",
            current_version_number: 1,
          },
        ],
        next_cursor: null,
      },
    }),
  );

  await page.goto("/author");
  await expect(page.getByRole("link", { name: "Untitled manuscript" })).toBeVisible();
  await page.getByLabel("Search manuscripts on this page").fill("draft");
  await expect(page.getByRole("link", { name: "Untitled manuscript" })).toHaveCount(0);
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
