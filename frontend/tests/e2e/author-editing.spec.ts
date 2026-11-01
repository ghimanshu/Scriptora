import { expect, test } from "@playwright/test";

for (const { status, replaceFile } of [
  ...["DRAFT", "SUBMITTED", "ASSIGNED", "REJECTED", "APPROVED"].map(status => ({ status, replaceFile: true })),
  { status: "REJECTED", replaceFile: false },
]) {
  test(`author editing follows ${status} lifecycle (${replaceFile ? "replacement document" : "existing document"})`, async ({ page }) => {
    const metadata = { title: "Original title", abstract: "Original abstract", keywords: ["research"], authors: [], declarations: { originality: true } };
    let article = {
      id: "article", title: metadata.title, abstract: metadata.abstract, status,
      lock_version: 1, current_version_id: "version", current_version_number: 1,
      created_at: "2026-10-01T00:00:00Z",
      current_version: { data: metadata, manuscript_file_id: "file" },
      // Stale action flags must not make submitted or approved articles editable.
      allowed_actions: status === "REJECTED" ? ["RESUBMIT"] : ["EDIT", "SUBMIT"],
    };
    let saved = false;
    let resubmitted = false;
    await page.route("**/api/v1/me", route => route.fulfill({ json: { id: "author", name: "Author", roles: ["AUTHOR"] } }));
    await page.route("**/api/v1/articles/article", async route => {
      if (route.request().method() === "PATCH") {
        expect(route.request().headers()["idempotency-key"]).toBeTruthy();
        expect(route.request().headers()["if-match"]).toBe("1");
        const payload = route.request().postDataJSON();
        expect(payload.metadata).toEqual({ ...metadata, title: "Edited title", abstract: "Edited abstract" });
        saved = true;
        article = { ...article, title: payload.metadata.title, abstract: payload.metadata.abstract, lock_version: 2, current_version: { ...article.current_version, data: payload.metadata } };
      }
      await route.fulfill({ json: article });
    });
    await page.route("**/api/v1/articles/article/timeline", route => route.fulfill({ json: [] }));
    await page.route("**/api/v1/articles/article/versions", async route => {
      if (route.request().method() === "POST") {
        expect(route.request().headers()["idempotency-key"]).toBeTruthy();
        expect(route.request().postDataJSON()).toEqual({ metadata: { ...metadata, title: "Edited title", abstract: "Edited abstract" }, manuscript_file_id: replaceFile ? "revision-file" : "file" });
        await route.fulfill({ json: { id: "revision" } });
      } else await route.fulfill({ json: [{ id: "version", version_number: 1, created_at: article.created_at, reviews: status === "REJECTED" ? [{ id: "review", decision: "REQUEST_REVISION", summary: "Please revise", comments: [{ id: "comment", text: "Clarify methods", section_ref: "Methods", required: true }] }] : [] }] });
    });
    await page.route("**/api/v1/files", route => route.fulfill({ json: { id: "revision-file", scan_status: "CLEAN" } }));
    await page.route("**/api/v1/articles/article/resubmit", async route => {
      expect(route.request().headers()["idempotency-key"]).toBeTruthy();
      expect(route.request().postDataJSON()).toEqual({ new_version_id: "revision", responses: { comment: "Methods clarified" }, expected_version: 1 });
      resubmitted = true;
      article = { ...article, status: "ASSIGNED", allowed_actions: [] };
      await route.fulfill({ json: article });
    });
    await page.goto("/author/articles/article");
    if (status === "DRAFT" || status === "REJECTED") {
      await page.getByLabel("Title", { exact: true }).fill("Edited title");
      await page.getByRole("textbox", { name: "Abstract", exact: true }).fill("Edited abstract");
      if (status === "DRAFT") {
        await page.getByRole("button", { name: "Save draft changes", exact: true }).click();
        await expect(page.getByRole("heading", { name: "Edited title", exact: true })).toBeVisible();
        expect(saved).toBe(true);
      } else {
        await page.getByLabel("Your response", { exact: true }).fill("Methods clarified");
        if (replaceFile) await page.getByLabel("Manuscript file", { exact: true }).setInputFiles({ name: "revision.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.7 revised manuscript") });
        if (replaceFile) await expect(page.getByText(/File received/)).toBeVisible();
        await page.getByRole("checkbox", { name: /I confirm the revised manuscript/ }).check();
        await page.getByRole("button", { name: "Confirm & resubmit revision", exact: true }).click();
        await expect(page.getByLabel("Title", { exact: true })).toHaveCount(0);
        expect(resubmitted).toBe(true);
        await expect(page.getByText("Assigned", { exact: true })).toBeVisible();
      }
    } else {
      await expect(page.getByText(/This article is read-only/)).toBeVisible();
      await expect(page.getByLabel("Title", { exact: true })).toHaveCount(0);
      await expect(page.getByRole("button", { name: "Confirm submission", exact: true })).toHaveCount(0);
    }
  });
}
