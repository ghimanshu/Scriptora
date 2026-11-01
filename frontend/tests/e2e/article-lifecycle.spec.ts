import { expect, test } from "@playwright/test";

const created_at = "2026-11-01T00:00:00Z";

test("admin saves fee and bank instructions with a fixed five-day review deadline", async ({ page }) => {
  let saved = false;
  await page.route("**/api/v1/me", route => route.fulfill({ json: { id: "admin", name: "Admin", roles: ["ADMIN"] } }));
  for (const kind of ["subjects", "outlets", "templates", "issues"]) {
    await page.route(`**/api/v1/admin/${kind}`, route => route.fulfill({ json: { items: [] } }));
  }
  await page.route("**/api/v1/admin/settings", async route => {
    if (route.request().method() === "POST") {
      expect(route.request().headers()["idempotency-key"]).toBeTruthy();
      expect(route.request().postDataJSON()).toEqual({ review_duration_hours: 120, publication_fee_minor: 25000, max_live_assignments: 3, payment_instructions: "Transfer to the publication bank account" });
      saved = true;
      await route.fulfill({ status: 201, json: {} });
    } else await route.fulfill({ json: { version: saved ? 2 : 1, values: { publication_fee_minor: 250000, max_live_assignments: 5, payment_instructions: "Original bank instructions" } } });
  });
  await page.goto("/admin/settings");
  await expect(page.getByLabel("Review deadline")).toHaveValue("5 days from assignment");
  await expect(page.getByLabel("Review deadline")).toHaveAttribute("readonly", "");
  await page.getByLabel("Publication fee (INR)", { exact: true }).fill("250");
  await page.getByLabel("Maximum active assignments per reviewer", { exact: true }).fill("3");
  await page.getByRole("textbox", { name: "Payment instructions", exact: true }).fill("Transfer to the publication bank account");
  await page.getByRole("button", { name: "Save settings", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Settings saved" })).toBeVisible();
  expect(saved).toBe(true);
});

test("admin assigns a subject-matched reviewer once", async ({ page }) => {
  let assigned = false;
  await page.route("**/api/v1/me", route => route.fulfill({ json: { id: "admin", name: "Admin", roles: ["ADMIN"] } }));
  await page.route("**/api/v1/articles/article", route => route.fulfill({ json: {
    id: "article", title: "Research article", status: assigned ? "ASSIGNED" : "SUBMITTED",
    lock_version: assigned ? 2 : 1, created_at, current_version_number: 1,
    allowed_actions: assigned ? [] : ["ASSIGN"],
    assignment: assigned ? { id: "assignment", state: "ACTIVE", due_at: "2026-11-06T00:00:00Z" } : null,
  } }));
  await page.route("**/api/v1/articles/article/versions", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/articles/article/timeline", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/admin/articles/article/reviewers", route => route.fulfill({ json: { items: [{ id: "reviewer", name: "Subject Expert", email: "expert@example.com" }] } }));
  await page.route("**/api/v1/admin/articles/article/assign", async route => {
    expect(route.request().headers()["idempotency-key"]).toBeTruthy();
    expect(route.request().postDataJSON()).toEqual({ reviewer_id: "reviewer", reason: "Matching subject expertise", expected_version: 1 });
    assigned = true;
    await route.fulfill({ json: { id: "assignment" } });
  });
  await page.goto("/admin/articles/article");
  await page.getByRole("combobox", { name: "Reviewer", exact: true }).selectOption("reviewer");
  await page.getByRole("textbox", { name: "Assignment reason" }).fill("Matching subject expertise");
  await page.getByRole("button", { name: "Assign reviewer", exact: true }).click();
  await expect(page.getByRole("button", { name: "Assign reviewer", exact: true })).toHaveCount(0);
  await expect(page.getByText("Assigned", { exact: true })).toBeVisible();
  await expect(page.getByText("Review deadline", { exact: true })).toBeVisible();
});

test("reviewer submits feedback using array assignments and backend review fields", async ({ page }) => {
  let completed = false;
  await page.route("**/api/v1/me", route => route.fulfill({ json: { id: "reviewer", name: "Reviewer", roles: ["REVIEWER"] } }));
  await page.route("**/api/v1/assignments/me?*", route => route.fulfill({ json: [{ id: "assignment", article_id: "article", title: "Research article", state: completed ? "COMPLETED" : "ACTIVE", due_at: "2026-11-06T00:00:00Z" }] }));
  await page.route("**/api/v1/articles/article", route => route.fulfill({ json: { id: "article", title: "Research article", status: "ASSIGNED", current_version_number: 1, lock_version: 2, created_at } }));
  await page.route("**/api/v1/articles/article/versions", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/assignments/assignment/review", async route => {
    const payload = route.request().postDataJSON();
    expect(route.request().headers()["idempotency-key"]).toBeTruthy();
    expect(payload.decision).toBe("REQUEST_REVISION");
    expect(payload.comments).toBe("Please explain the methods in more detail.");
    expect(payload.numbered_comments).toEqual([{ section_ref: "Methods", text: "Explain the sample size.", required: true }]);
    completed = true;
    await route.fulfill({ json: { id: "review" } });
  });
  await page.goto("/reviewer/assignments/assignment");
  await page.getByRole("textbox", { name: "Overall feedback", exact: true }).fill("Please explain the methods in more detail.");
  await page.getByRole("button", { name: "+ Add comment", exact: true }).click();
  await page.getByLabel("Section or page reference", { exact: true }).fill("Methods");
  await page.getByRole("textbox", { name: "Comment", exact: true }).fill("Explain the sample size.");
  await page.getByRole("checkbox", { name: /I confirm this final review/ }).check();
  await page.getByRole("button", { name: "Confirm & submit review", exact: true }).click();
  await expect(page.getByRole("status").filter({ hasText: "Review submitted" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Confirm & submit review", exact: true })).toHaveCount(0);
  expect(completed).toBe(true);
});

test("payment proof sets paid and admin verification sets payment approved", async ({ page }) => {
  let paid = false;
  let verified = false;
  let admin = false;
  const attempt = { id: "attempt", invoice_id: "invoice", proof_file_id: "proof", amount_minor: 250000, reference: "UTR123", currency: "INR" };
  await page.route("**/api/v1/me", route => route.fulfill({ json: { id: admin ? "admin" : "author", name: "Account", roles: [admin ? "ADMIN" : "AUTHOR"] } }));
  await page.route("**/api/v1/articles/article", route => route.fulfill({ json: { id: "article", title: "Research article", status: verified ? "PAYMENT_APPROVED" : paid ? "PAID" : "APPROVED", current_version_number: 1, created_at, allowed_actions: ["VIEW_INVOICE"] } }));
  await page.route("**/api/v1/articles/article/versions", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/articles/article/timeline", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/articles/article/invoice", route => route.fulfill({ json: { id: "invoice", amount_minor: 250000, currency: "INR", status: verified ? "PAID" : "OPEN", instructions: "Pay to the publication bank account." } }));
  await page.route("**/api/v1/invoices/invoice/payment-attempts", async route => {
    if (route.request().method() === "POST") {
      const payload = route.request().postDataJSON();
      expect(payload.reference).toBe("UTR123");
      expect(payload.paid_at).toMatch(/^2026-10-31T/);
      expect(payload.proof_file_id).toBe("proof");
      expect(route.request().headers()["idempotency-key"]).toBeTruthy();
      paid = true;
      await route.fulfill({ json: { ...attempt, status: "SUBMITTED" } });
    } else await route.fulfill({ json: paid ? [{ ...attempt, status: verified ? "VERIFIED" : "SUBMITTED" }] : [] });
  });
  await page.route("**/api/v1/files", route => route.fulfill({ json: { id: "proof", scan_status: "CLEAN" } }));
  await page.route("**/api/v1/admin/payment-attempts/attempt/verify", async route => {
    expect(route.request().postDataJSON()).toEqual({ reference: "UTR123", receipt_confirmed: true, receipt_note: "Receipt checked in bank records" });
    expect(route.request().headers()["idempotency-key"]).toBeTruthy();
    verified = true;
    await route.fulfill({ json: { ...attempt, status: "VERIFIED" } });
  });
  await page.goto("/author/articles/article");
  await page.getByLabel("Transaction reference / UTR", { exact: true }).fill("UTR123");
  await page.getByLabel("Payment date", { exact: true }).fill("2026-10-31");
  await page.getByLabel("Payment proof", { exact: true }).setInputFiles({ name: "proof.png", mimeType: "image/png", buffer: Buffer.from("payment screenshot") });
  await expect(page.getByText(/File received/)).toBeVisible();
  await page.getByRole("button", { name: "Submit payment proof", exact: true }).click();
  await expect(page.getByText("Paid (awaiting verification)", { exact: true })).toBeVisible();
  admin = true;
  await page.goto("/admin/articles/article");
  await page.getByLabel("Verified bank reference", { exact: true }).fill("UTR123");
  await page.getByRole("textbox", { name: "Reconciliation note", exact: true }).fill("Receipt checked in bank records");
  await page.getByRole("checkbox", { name: /I checked the actual receipt/ }).check();
  await page.getByRole("button", { name: "Confirm verification", exact: true }).click();
  await expect(page.getByText("Payment approved", { exact: true })).toBeVisible();
});
