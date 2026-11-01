import { expect, test } from "@playwright/test";

const subject = { id: "123e4567-e89b-42d3-a456-426614174001", name: "Medicine" };
const type = { id: "123e4567-e89b-42d3-a456-426614174002", name: "Journal Article" };
const outlet = { id: "123e4567-e89b-42d3-a456-426614174003", name: "Medical Journal", type_id: type.id, template_id: "123e4567-e89b-42d3-a456-426614174004" };

test("submission wizard renders array taxonomy responses and handles selection", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/api/v1/me", route => route.fulfill({ json: { id: "author", name: "Author", roles: ["AUTHOR"] } }));
  await page.route("**/api/v1/subjects", route => route.fulfill({ json: [subject] }));
  await page.route("**/api/v1/publication-types", route => route.fulfill({ json: [type] }));
  await page.route("**/api/v1/outlets", route => route.fulfill({ json: [outlet] }));
  await page.route(`**/api/v1/templates/${outlet.template_id}`, route => route.fulfill({ json: { instructions: "Prepare your manuscript" } }));
  let savedDraft = false;
  let savedSubject = false;
  await page.route("**/api/v1/articles", async route => {
    const payload = route.request().postDataJSON();
    expect(payload.metadata.authors).toEqual([]);
    expect(payload.publication_type_id).toBe(type.id);
    expect(payload.outlet_id).toBe(outlet.id);
    expect(payload.template_id).toBe(outlet.template_id);
    expect(payload.primary_subject_id).toBeNull();
    expect(route.request().headers()["idempotency-key"]).toBeTruthy();
    savedDraft = true;
    await route.fulfill({ status: 201, json: { id: "draft", status: "DRAFT", lock_version: 1 } });
  });
  await page.route("**/api/v1/articles/draft", async route => {
    expect(route.request().method()).toBe("PATCH");
    expect(route.request().headers()["if-match"]).toBe("1");
    const payload = route.request().postDataJSON();
    expect(payload.publication_type_id).toBe(type.id);
    expect(payload.outlet_id).toBe(outlet.id);
    expect(payload.template_id).toBe(outlet.template_id);
    expect(payload.primary_subject_id).toBe(subject.id);
    expect(payload.metadata.title).toBe("New research");
    savedSubject = true;
    await route.fulfill({ json: { id: "draft", status: "DRAFT", lock_version: 2 } });
  });
  await page.goto("/author/articles/new");
  await expect(page.getByLabel("Publication type").getByRole("option", { name: type.name })).toHaveCount(1);
  await page.getByLabel("Publication type").selectOption(type.id);
  await page.getByLabel("Publication outlet").selectOption(outlet.id);
  await expect(page.getByLabel("Primary subject")).toHaveCount(0);
  await expect(page.getByLabel("Publication type")).toHaveValue(type.id);
  await expect(page.getByLabel("Publication outlet")).toHaveValue(outlet.id);
  await page.getByRole("button", { name: /Save & continue/ }).click();
  await expect(page.getByLabel("Article title")).toBeVisible();
  await expect(page.getByRole("link", { name: /Open saved draft/ })).toBeVisible();
  expect(savedDraft).toBe(true);
  await page.getByRole("combobox", { name: "Primary subject", exact: true }).selectOption(subject.id);
  await page.getByLabel("Article title").fill("New research");
  await page.getByRole("textbox", { name: "Abstract", exact: true }).fill("Research abstract");
  await page.getByLabel("Keywords").fill("science");
  await page.getByLabel("Corresponding author").fill("Test Author");
  await page.getByLabel("Author email").fill("author@example.com");
  await page.getByLabel("Affiliation").fill("Test University");
  await page.getByRole("button", { name: /Save & continue/ }).click();
  await expect(page.getByText("A shared commitment to good publishing", { exact: true })).toBeVisible();
  expect(savedSubject).toBe(true);
  expect(errors).toEqual([]);
});

test("submission wizard renders empty taxonomy arrays without crashing", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/api/v1/me", route => route.fulfill({ json: { id: "author", name: "Author", roles: ["AUTHOR"] } }));
  await page.route(/\/api\/v1\/(subjects|publication-types|outlets)$/, route => route.fulfill({ json: [] }));
  await page.goto("/author/articles/new");
  await expect(page.getByLabel("Publication type")).toBeVisible();
  for (const name of ["Publication type", "Publication outlet"]) {
    await expect(page.getByLabel(name).getByRole("option")).toHaveCount(1);
  }
  await expect(page.getByLabel("Primary subject")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("catalog renders array subject and outlet options", async ({ page }) => {
  await page.route("**/api/v1/subjects", route => route.fulfill({ json: [subject] }));
  await page.route("**/api/v1/outlets", route => route.fulfill({ json: [outlet] }));
  await page.route("**/api/v1/public/articles?**", route => route.fulfill({ json: { items: [], next_cursor: null } }));
  await page.goto("/articles");
  await expect(page.getByLabel("Subject", { exact: true }).getByRole("option", { name: subject.name })).toHaveCount(1);
  await expect(page.getByLabel("Outlet", { exact: true }).getByRole("option", { name: outlet.name })).toHaveCount(1);
});

test("reviewer subjects use the backend array of subscribed IDs", async ({ page }) => {
  await page.route("**/api/v1/me", route => route.fulfill({ json: { id: "reviewer", name: "Reviewer", roles: ["REVIEWER"] } }));
  await page.route("**/api/v1/subjects", route => route.fulfill({ json: [subject] }));
  await page.route("**/api/v1/reviewers/me/subjects", route => route.fulfill({ json: [subject.id] }));
  await page.goto("/reviewer/profile");
  await expect(page.getByRole("checkbox", { name: subject.name })).toBeChecked();
  let savedSubjects = false;
  await page.route("**/api/v1/reviewers/me/subjects", async route => {
    if (route.request().method() === "PUT") {
      expect(route.request().headers()["idempotency-key"]).toMatch(/^[\da-f-]{36}$/);
      expect(route.request().postDataJSON()).toEqual({ subject_ids: [subject.id] });
      savedSubjects = true;
      await route.fulfill({ status: 204 });
    } else await route.fulfill({ json: [subject.id] });
  });
  await page.getByRole("button", { name: "Save expertise", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Expertise subscriptions updated.");
  expect(savedSubjects).toBe(true);
  await page.route("**/api/v1/reviewers/me/availability", async route => {
    expect(route.request().method()).toBe("PATCH");
    expect(route.request().headers()["idempotency-key"]).toMatch(/^[\da-f-]{36}$/);
    expect(route.request().postDataJSON()).toEqual({ available: false });
    await route.fulfill({ status: 204 });
  });
  await page.getByLabel("Accept new assignments").selectOption("false");
  await page.getByRole("button", { name: "Update availability", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Availability updated.");
  await page.route("**/api/v1/review-queue?**", route => route.fulfill({ json: { items: [], next_cursor: null } }));
  await page.goto("/reviewer/queue");
  await expect(page.getByLabel("Filter by subject").getByRole("option", { name: subject.name })).toHaveCount(1);
});
