import { expect, test } from "@playwright/test";

test("admin can delete a published article with a reason", async ({ page }) => {
  await page.route("**/api/v1/me", route => route.fulfill({ json: { id: "admin", name: "Admin", roles: ["ADMIN"] } }));
  await page.route("**/api/v1/articles/article", route => route.fulfill({ json: {
    id: "article", title: "Published manuscript", status: "PUBLISH", created_at: "2026-10-01T00:00:00Z",
  } }));
  await page.route("**/api/v1/articles/article/versions", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/articles/article/timeline", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/admin/articles?*", route => route.fulfill({ json: { items: [], next_cursor: null } }));
  let calls = 0;
  await page.route("**/api/v1/admin/articles/article", async route => {
    calls++;
    expect(route.request().method()).toBe("DELETE");
    expect(route.request().postDataJSON()).toEqual({ reason: "Duplicate publication" });
    expect(route.request().headers()["idempotency-key"]).toBeTruthy();
    await route.fulfill({ json: { deleted: true, article_id: "article" } });
  });
  await page.goto("/admin/articles/article");
  const button = page.getByRole("button", { name: "Delete article and notify author" });
  await expect(button).toBeDisabled();
  await page.getByLabel("Reason for deletion").fill("   ");
  await expect(button).toBeDisabled();
  await page.getByLabel("Reason for deletion").fill("  Duplicate publication  ");
  await button.click();
  await expect(page).toHaveURL(/\/admin\/articles$/);
  expect(calls).toBe(1);
});

test("authors have no admin deletion form", async ({ page }) => {
  await page.route("**/api/v1/me", route => route.fulfill({ json: { id: "author", name: "Author", roles: ["AUTHOR"] } }));
  await page.route("**/api/v1/articles/article", route => route.fulfill({ json: {
    id: "article", title: "Author manuscript", status: "SUBMITTED", created_at: "2026-10-01T00:00:00Z",
  } }));
  await page.route("**/api/v1/articles/article/versions", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/articles/article/timeline", route => route.fulfill({ json: [] }));
  await page.goto("/author/articles/article");
  await expect(page.getByRole("heading", { name: "Author manuscript", exact: true })).toBeVisible();
  await expect(page.getByLabel("Reason for deletion")).toHaveCount(0);
});
