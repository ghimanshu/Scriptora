import { expect, test } from "@playwright/test";

const rows = ["DRAFT", "SUBMITTED", "ASSIGNED", "REJECTED", "APPROVED", "PAID", "PAYMENT_APPROVED", "PUBLISH"].map(status => ({
  id: status.toLowerCase(), title: `${status} article`, status, current_version_number: 1, created_at: "2026-11-01T00:00:00Z",
}));

test("author action column only has draft deletion with an explanatory confirmation popup", async ({ page }) => {
  let deleted = false;
  await page.route("**/api/v1/me", route => route.fulfill({ json: { id: "author", name: "Author", roles: ["AUTHOR"] } }));
  await page.route("**/api/v1/articles", route => route.fulfill({ json: { items: deleted ? rows.slice(1) : rows } }));
  await page.route("**/api/v1/articles/draft", async route => {
    expect(route.request().method()).toBe("DELETE");
    expect(route.request().headers()["idempotency-key"]).toBeTruthy();
    expect(route.request().postDataJSON()).toEqual({ reason: "Duplicate draft" });
    deleted = true;
    await route.fulfill({ json: { deleted: true, article_id: "draft" } });
  });
  await page.goto("/author/articles");
  await expect(page.getByRole("button", { name: /^Delete / })).toHaveCount(1);
  const draft = page.getByRole("row").filter({ hasText: "DRAFT article" });
  await expect(draft.getByRole("button")).toHaveCount(1);
  await expect(page.getByRole("link", { name: "DRAFT article", exact: true })).toHaveAttribute("href", "/author/articles/draft");
  await expect(page.getByRole("row").filter({ hasText: "SUBMITTED article" }).getByRole("button")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^(Edit|View)$/ })).toHaveCount(0);
  await draft.getByRole("button", { name: "Delete DRAFT article", exact: true }).click();
  const popup = page.getByRole("dialog", { name: "Delete this draft?", exact: true });
  await expect(popup).toBeVisible();
  await expect(popup).toContainText("Only drafts can be deleted.");
  await expect(popup).toContainText("DRAFT article");
  expect(deleted).toBe(false);
  await popup.press("Escape");
  await expect(popup).not.toBeVisible();
  await expect(draft.getByRole("button", { name: "Delete DRAFT article", exact: true })).toBeFocused();
  await draft.getByRole("button", { name: "Delete DRAFT article", exact: true }).click();
  await popup.getByRole("button", { name: "Cancel", exact: true }).click();
  expect(deleted).toBe(false);
  await draft.getByRole("button", { name: "Delete DRAFT article", exact: true }).click();
  await popup.getByLabel("Reason for deletion (optional)", { exact: true }).fill("Duplicate draft");
  await popup.getByRole("button", { name: "Delete draft", exact: true }).click();
  await expect(page.getByText("DRAFT article", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Delete / })).toHaveCount(0);
  await expect(page.getByText("SUBMITTED article", { exact: true })).toBeVisible();
});

test("admin cannot delete a published article", async ({ page }) => {
  await page.route("**/api/v1/me", route => route.fulfill({ json: { id: "admin", name: "Admin", roles: ["ADMIN"] } }));
  await page.route("**/api/v1/articles/article", route => route.fulfill({ json: { id: "article", title: "Published article", status: "PUBLISH", created_at: "2026-11-01T00:00:00Z" } }));
  await page.route("**/api/v1/articles/article/versions", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/articles/article/timeline", route => route.fulfill({ json: [] }));
  await page.goto("/admin/articles/article");
  await expect(page.getByRole("heading", { name: "Published article", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /Delete/ })).toHaveCount(0);
});
