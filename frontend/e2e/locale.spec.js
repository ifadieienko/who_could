import { awaitSelect } from "./select.js";
import { test, expect } from "@playwright/test";
const selector = (page) =>
  page.getByRole("combobox", { name: "Language / Язык / Język" });

test("language is global, persistent and preserves drafts without changing organization defaults", async ({
  page,
}) => {
  await page.goto("/");
  await awaitSelect(selector(page), "en");
  await page.getByLabel("Email", { exact: true }).fill("locale@example.com");
  await awaitSelect(selector(page), "pl");
  await expect(page.getByLabel("Email", { exact: true })).toHaveValue(
    "locale@example.com",
  );
  await expect(
    page.getByRole("heading", { name: "Zaloguj się do warsztatu" }),
  ).toBeVisible();
  await page.reload();
  await expect(selector(page)).toHaveAttribute("data-value", "pl");
  await awaitSelect(selector(page), "en");
  await page.getByRole("button", { name: "New workshop", exact: true }).click();
  await page.getByLabel("Your name").fill("Locale owner");
  await page.getByLabel("Workshop name").fill("Language demo");
  await page.getByLabel("Email", { exact: true }).fill("locale@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("browser-password-123");
  await page.getByRole("button", { name: "Get started" }).click();
  await page.getByRole("button", { name: "Customers", exact: true }).click();
  await page.getByRole("button", { name: "New customer", exact: true }).click();
  await page.getByLabel("Name", { exact: true }).fill("Unsaved customer");
  await awaitSelect(selector(page), "ru");
  await expect(page.getByLabel("Название", { exact: true })).toHaveValue(
    "Unsaved customer",
  );
  await expect(page.locator("html")).toHaveAttribute("lang", "ru");
  await page.getByRole("button", { name: "Организация", exact: true }).click();
  await expect(
    page.getByLabel("Язык организации по умолчанию"),
  ).toHaveAttribute("data-value", "en");
  await page.reload();
  await expect(selector(page)).toHaveAttribute("data-value", "ru");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  const box = await selector(page).boundingBox();
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.y + box.height).toBeLessThan(65);
  expect(box.x + box.width).toBeLessThanOrEqual(390);
  for (const path of ["/reset/test-token", "/quote/test-token"]) {
    await page.goto(path);
    await expect(selector(page)).toHaveAttribute("data-value", "ru");
    await awaitSelect(selector(page), "en");
    await expect(selector(page)).toHaveAttribute("data-value", "en");
    await awaitSelect(selector(page), "ru");
  }
});
