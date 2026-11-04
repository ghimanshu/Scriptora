import { expect, test } from "@playwright/test";

for (const area of ["author", "reviewer", "admin"]) {
  test(`${area} sees unread dashboard and navigation counts and can manage notifications`, async ({ page }) => {
    const items = [
      { id: "update", title: "Article approved", message: "Your article has been approved.", type: "ARTICLE_APPROVED", payload: { article_title: "Research manuscript" }, created_at: "2026-11-02T10:00:00Z", read_at: null as string | null },
      { id: "older", title: "Reviewer assigned", message: "A reviewer has been assigned.", type: "ASSIGNED", payload: { article_title: "Research manuscript" }, created_at: "2026-11-01T10:00:00Z", read_at: "2026-11-01T11:00:00Z" as string | null },
    ];
    const summary = () => ({ unread_count: items.filter(item => !item.read_at).length, total_count: items.length, items });
    await page.route("**/api/v1/me", route => route.fulfill({ json: { id: area, name: "Test Account", roles: [area.toUpperCase()] } }));
    await page.route("**/api/v1/articles", route => route.fulfill({ json: { items: [] } }));
    await page.route("**/api/v1/admin/articles", route => route.fulfill({ json: { items: [] } }));
    await page.route("**/api/v1/assignments/me", route => route.fulfill({ json: [] }));
    await page.route("**/api/v1/notifications/summary", route => route.fulfill({ json: summary() }));
    await page.route("**/api/v1/notifications?*", route => {
      const status = new URL(route.request().url()).searchParams.get("status");
      const filtered = items.filter(item => status === "unread" ? !item.read_at : status === "read" ? !!item.read_at : true);
      return route.fulfill({ json: { ...summary(), items: filtered, next_cursor: null } });
    });
    for (const action of ["read", "unread"]) {
      await page.route(`**/api/v1/notifications/update/${action}`, route => {
        expect(route.request().method()).toBe("POST");
        expect(route.request().headers()["idempotency-key"]).toBeTruthy();
        items[0].read_at = action === "read" ? "2026-11-02T12:00:00Z" : null;
        return route.fulfill({ json: items[0] });
      });
    }
    await page.route("**/api/v1/notifications/read-all", route => {
      expect(route.request().headers()["idempotency-key"]).toBeTruthy();
      for (const item of items) item.read_at = "2026-11-02T12:00:00Z";
      return route.fulfill({ json: { unread_count: 0, updated_count: 1 } });
    });
    await page.goto(`/${area}`);
    await expect(page.getByRole("heading", { name: "1 unread notification", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Notifications, 1 unread", exact: true })).toBeVisible();
    await expect(page.getByLabel("Notification summary")).toContainText("Article approved");
    await page.getByRole("link", { name: "View all notifications", exact: true }).click();
    await page.waitForURL(`**/${area}/notifications`);
    await expect(page.getByRole("heading", { name: "Notifications", exact: true })).toBeVisible();
    const update = page.getByRole("article").filter({ hasText: "Article approved" });
    await expect(update.getByText("Unread", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Mark as read: Article approved", exact: true }).click();
    await expect(update.getByText("Read", { exact: true })).toBeVisible();
    await expect(page.getByText("0 unread notifications", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Notifications, 1 unread", exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: "Mark as unread: Article approved", exact: true }).click();
    await expect(page.getByRole("link", { name: "Notifications, 1 unread", exact: true })).toBeVisible();
    await page.getByRole("group", { name: "Filter notifications" }).getByRole("button", { name: "Unread", exact: true }).click();
    await expect(page.getByRole("article")).toHaveCount(1);
    await page.getByRole("button", { name: "Mark all as read", exact: true }).click();
    await expect(page.getByRole("heading", { name: "No unread notifications", exact: true })).toBeVisible();
    await page.getByRole("group", { name: "Filter notifications" }).getByRole("button", { name: "Read", exact: true }).click();
    await expect(page.getByRole("article")).toHaveCount(2);
  });
}

test("returning to the window refreshes unread updates without reloading the dashboard", async ({ page }) => {
  let count = 0;
  const items = () => Array.from({ length: count }, (_, index) => ({ id: `remote-${index}`, title: `Remote update ${index + 1}`, message: "An article update arrived.", created_at: "2026-11-02T10:00:00Z", read_at: null }));
  await page.route("**/api/v1/me", route => route.fulfill({ json: { id: "author", name: "Author", roles: ["AUTHOR"] } }));
  await page.route("**/api/v1/articles", route => route.fulfill({ json: { items: [] } }));
  await page.route("**/api/v1/notifications/summary", route => route.fulfill({ json: { unread_count: count, total_count: count, items: items() } }));
  await page.route("**/api/v1/notifications?*", route => route.fulfill({ json: { unread_count: count, total_count: count, items: items(), next_cursor: null } }));
  await page.goto("/author");
  await expect(page.getByRole("heading", { name: "0 unread notifications", exact: true })).toBeVisible();
  count = 1;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("heading", { name: "1 unread notification", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Notifications, 1 unread", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "View all notifications", exact: true }).click();
  await page.waitForURL("**/author/notifications");
  await expect(page.getByRole("article")).toHaveCount(1);
  count = 2;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("article")).toHaveCount(2);
  await expect(page.getByText("2 unread notifications", { exact: true })).toBeVisible();
});
