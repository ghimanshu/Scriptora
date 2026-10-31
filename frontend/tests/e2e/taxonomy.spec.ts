import { expect, test } from "@playwright/test";

const subject = { id: "123e4567-e89b-42d3-a456-426614174001", name: "Medicine" };
const type = { id: "123e4567-e89b-42d3-a456-426614174002", name: "Journal Article" };
const outlet = { id: "123e4567-e89b-42d3-a456-426614174003", name: "Medical Journal" };

test("submission wizard renders array taxonomy responses and handles selection", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/api/v1/me", route => route.fulfill({ json: { id: "author", name: "Author", roles: ["AUTHOR"] } }));
  await page.route("**/api/v1/subjects", route => route.fulfill({ json: [subject] }));
  await page.route("**/api/v1/publication-types", route => route.fulfill({ json: [type] }));
  await page.route("**/api/v1/outlets", route => route.fulfill({ json: [outlet] }));
  await page.goto("/author/articles/new");
  await expect(page.getByLabel("Publication type").getByRole("option", { name: type.name })).toHaveCount(1);
  await page.getByLabel("Publication type").selectOption(type.id);
  await page.getByLabel("Publication outlet").selectOption(outlet.id);
  await page.getByLabel("Primary subject").selectOption(subject.id);
  await expect(page.getByLabel("Publication type")).toHaveValue(type.id);
  await expect(page.getByLabel("Publication outlet")).toHaveValue(outlet.id);
  await expect(page.getByLabel("Primary subject")).toHaveValue(subject.id);
  expect(errors).toEqual([]);
});

test("submission wizard renders empty taxonomy arrays without crashing", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/api/v1/me", route => route.fulfill({ json: { id: "author", name: "Author", roles: ["AUTHOR"] } }));
  await page.route(/\/api\/v1\/(subjects|publication-types|outlets)$/, route => route.fulfill({ json: [] }));
  await page.goto("/author/articles/new");
  await expect(page.getByLabel("Publication type")).toBeVisible();
  for (const name of ["Publication type", "Publication outlet", "Primary subject"]) {
    await expect(page.getByLabel(name).getByRole("option")).toHaveCount(1);
  }
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
  await page.route("**/api/v1/review-queue?**", route => route.fulfill({ json: { items: [], next_cursor: null } }));
  await page.goto("/reviewer/queue");
  await expect(page.getByLabel("Filter by subject").getByRole("option", { name: subject.name })).toHaveCount(1);
});
