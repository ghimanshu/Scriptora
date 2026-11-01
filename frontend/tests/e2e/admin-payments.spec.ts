import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/me", (route) => route.fulfill({
    json: { id: "admin", name: "Admin", roles: ["ADMIN"] },
  }));
});

test("admin payments renders an empty array response", async ({ page }) => {
  await page.route("**/api/v1/admin/payments", (route) => route.fulfill({ json: [] }));
  await page.goto("/admin/payments");
  await expect(page.getByRole("heading", { name: "All caught up" })).toBeVisible();
});

test("admin payments renders payment records from an array response", async ({ page }) => {
  await page.route("**/api/v1/admin/payments", (route) => route.fulfill({ json: [{
    id: "payment", invoice_id: "invoice", proof_file_id: "proof", status: "SUBMITTED",
    reference: "BANK-123", amount_minor: 12500, currency: "INR",
  }] }));
  await page.goto("/admin/payments");
  await expect(page.getByText("Reference: BANK-123", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: /Download proof/ })).toHaveAttribute("href", "/api/v1/files/proof/download");
});
