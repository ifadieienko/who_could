import { test, expect } from "@playwright/test";
import { awaitSelect } from "./select.js";
async function register(page, email) {
  await page.goto("/");
  await awaitSelect(
    page.getByRole("combobox", { name: "Language / Язык / Język" }),
    "en",
  );
  await page.getByRole("button", { name: "New workshop", exact: true }).click();
  await page.getByLabel("Your name").fill("Conditions owner");
  await page.getByLabel("Workshop name").fill("Conditions demo");
  await page.getByLabel("Email", { exact: true }).fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill("browser-password-123");
  await page.getByRole("button", { name: "Get started" }).click();
}
test("warehouse badge contrast, team columns and form input alignment", async ({
  page,
}) => {
  await register(page, "layout-fixes@example.com");
  await page.getByRole("button", { name: "Warehouse", exact: true }).click();
  for (const theme of ["Light", "Dark"]) {
    for (const accent of ["Green", "Red", "Violet"]) {
      await page
        .getByRole("button", { name: "Appearance", exact: true })
        .click();
      await page.getByRole("radio", { name: theme, exact: true }).check();
      await page.getByRole("radio", { name: accent, exact: true }).check();
      await page.keyboard.press("Escape");
      const badge = page.locator(".warehouse-title .badge");
      await expect(badge).toHaveText("1 колонка");
      const ratio = await badge.evaluate((el) => {
        const s = getComputedStyle(el);
        const lum = (c) => {
          const v = c
            .match(/[\d.]+/g)
            .slice(0, 3)
            .map(Number)
            .map((v) => {
              v /= 255;
              return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
            });
          return v[0] * 0.2126 + v[1] * 0.7152 + v[2] * 0.0722;
        };
        const a = lum(s.color),
          b = lum(s.backgroundColor);
        return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
      });
      expect(ratio).toBeGreaterThanOrEqual(4.5);
    }
  }
  await page.getByRole("button", { name: "Team", exact: true }).click();
  await expect(page.locator(".w-team-owner")).toHaveText("Владелец");
  await expect(page.locator(".w-team-status")).toHaveText("Доступ открыт");
  expect(
    await page
      .locator(".w-team-table tbody td")
      .nth(1)
      .evaluate((el) => parseFloat(getComputedStyle(el).borderLeftWidth)),
  ).toBeGreaterThan(0);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBeTruthy();
  await page.setViewportSize({ width: 1545, height: 900 });
  await page.getByRole("button", { name: "Forms", exact: true }).click();
  // Read both rectangles in one frame while the panel animates on entry.
  await expect
    .poll(() =>
      page.evaluate(() => {
        const a = document
          .querySelector('input[aria-label="Название формы"]')
          .getBoundingClientRect();
        const b = document
          .querySelector('input[aria-label="Назначение формы"]')
          .getBoundingClientRect();
        return Math.max(Math.abs(a.y - b.y), Math.abs(a.height - b.height));
      }),
    )
    .toBeLessThan(1);
});
test("condition editor combines comparisons and preserves published rules", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await register(page, "conditions-ui@example.com");
  await page.getByRole("button", { name: "Forms", exact: true }).click();
  await page
    .getByLabel("Название формы", { exact: true })
    .fill("Conditional inspection");
  await page
    .getByLabel("Назначение формы", { exact: true })
    .fill("measurement");
  const first = page.locator(".w-field-editor").first();
  await first.getByLabel("Название", { exact: true }).fill("Temperature");
  await awaitSelect(first.getByLabel("Тип", { exact: true }), "number");
  await page.getByRole("button", { name: "+ Поле", exact: true }).click();
  const second = page.locator(".w-field-editor").nth(1);
  await second.getByLabel("Название", { exact: true }).fill("Reason");
  await second.getByText("Условия и права", { exact: true }).click();
  await second
    .getByRole("button", { name: "Add condition", exact: true })
    .click();
  await awaitSelect(second.getByLabel("Comparison"), "gte");
  await second.getByLabel("Value", { exact: true }).fill("10");
  await second.getByRole("button", { name: "Combine rules" }).click();
  await second.getByRole("button", { name: "Add rule", exact: true }).click();
  const rule = second.locator(".w-condition-rule").nth(1);
  await awaitSelect(rule.getByLabel("Comparison"), "lte");
  await rule.getByLabel("Value", { exact: true }).fill("20");
  const preview = page.locator(".w-dynamic");
  await preview.getByLabel(/Temperature/).fill("5");
  await expect(preview.getByLabel(/Reason/)).toHaveCount(0);
  await preview.getByLabel(/Temperature/).fill("12");
  await expect(preview.getByLabel(/Reason/)).toBeVisible();
  await awaitSelect(second.getByLabel("Rule combination"), "any");
  await preview.getByLabel(/Temperature/).fill("25");
  await expect(preview.getByLabel(/Reason/)).toBeVisible();
  await awaitSelect(second.getByLabel("Rule combination"), "all");
  await expect(preview.getByLabel(/Reason/)).toHaveCount(0);
  const saved = page.waitForResponse(
    (r) => r.url().endsWith("/v2/templates") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Сохранить черновик", exact: true })
    .click();
  const response = await saved;
  expect(response.ok(), await response.text()).toBeTruthy();
  const template = response.request().postDataJSON();
  expect(template.fields[1].condition.all.map((r) => r.operator)).toEqual([
    "gte",
    "lte",
  ]);
  await page
    .getByRole("button", { name: "Опубликовать сохранённую версию" })
    .click();
  await expect(
    page.getByText("Опубликованная версия неизменяема.", { exact: false }),
  ).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: /Conditional inspection/ }).click();
  await expect(second.getByLabel("Value", { exact: true }).first()).toHaveValue(
    "10",
  );
  expect(errors).toEqual([]);
});
