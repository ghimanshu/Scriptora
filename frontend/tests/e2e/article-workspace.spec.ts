import { expect, test } from "@playwright/test";

for (const actions of [undefined, null, ["ASSIGN"]]) {
  test(`admin workspace handles allowed_actions=${JSON.stringify(actions)}`, async ({ page }) => {
    await page.route("**/api/v1/me", (route) => route.fulfill({ json: { id: "admin", name: "Admin", roles: ["ADMIN"] } }));
    await page.route("**/api/v1/articles/article", (route) => route.fulfill({ json: {
      id: "article", title: "Test manuscript", status: "SUBMITTED", created_at: "2026-10-01T00:00:00Z",
      current_version_number: 1, allowed_actions: actions,
    } }));
    await page.route("**/api/v1/articles/article/versions", (route) => route.fulfill({ json: [
      { id: "version", version_number: 1, created_at: "2026-10-01T00:00:00Z", manuscript_file_id: "manuscript" },
    ] }));
    await page.route("**/api/v1/articles/article/timeline", (route) => route.fulfill({ json: [
      { id: "event", event_type: "SUBMITTED", description: "Manuscript submitted for review", created_at: "2026-10-01T00:00:00Z" },
    ] }));
    await page.route("**/api/v1/admin/articles/article/reviewers", route => route.fulfill({ json: { items: [] } }));
    await page.goto("/admin/articles/article");
    await expect(page.getByRole("heading", { name: "Test manuscript", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: /Download manuscript/ })).toBeVisible();
    await expect(page.getByText("Manuscript submitted for review", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Assign a reviewer", exact: true })).toHaveCount(actions ? 1 : 0);
  });
}
