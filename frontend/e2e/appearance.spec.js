import { test, expect } from "@playwright/test";
import { awaitSelect } from "./select.js";
test("appearance persists, menus support keyboard and remain readable in both themes", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  const language = page.getByRole("combobox", {
    name: "Language / Язык / Język",
  });
  await awaitSelect(language, "en");
  await page.getByRole("button", { name: "Appearance", exact: true }).click();
  await page.getByRole("radio", { name: "Dark", exact: true }).check();
  await page.getByRole("radio", { name: "Violet", exact: true }).check();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("html")).toHaveAttribute("data-accent", "violet");
  await page.keyboard.press("Escape");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("html")).toHaveAttribute("data-accent", "violet");
  await language.focus();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("listbox")).toBeVisible();
  await page.keyboard.press("End");
  await page.keyboard.press("Enter");
  await expect(language).toHaveAttribute("data-value", "ru");
  await awaitSelect(language, "en");
  await page.getByRole("button", { name: "New workshop", exact: true }).click();
  await page.getByLabel("Your name").fill("Appearance owner");
  await page.getByLabel("Workshop name").fill("Contrast demo");
  await page
    .getByLabel("Email", { exact: true })
    .fill("appearance@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("browser-password-123");
  await page.getByRole("button", { name: "Get started" }).click();
  const organization = page.getByRole("combobox", {
    name: "Organization",
    exact: true,
  });
  await expect(organization).toBeVisible();
  for (const theme of ["Light", "Dark"]) {
    await page.getByRole("button", { name: "Appearance", exact: true }).click();
    await page.getByRole("radio", { name: theme, exact: true }).check();
    await page.getByRole("radio", { name: "Red", exact: true }).check();
    await page.keyboard.press("Escape");
    await organization.click();
    await expect(
      page.getByRole("option", { name: "Contrast demo", exact: true }),
    ).toBeVisible();
    const ratio = await organization.evaluate((el) => {
      const style = getComputedStyle(el);
      const luminance = (color) => {
        const c = color
          .match(/[\d.]+/g)
          .slice(0, 3)
          .map(Number)
          .map((v) => {
            v /= 255;
            return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
          });
        return c[0] * 0.2126 + c[1] * 0.7152 + c[2] * 0.0722;
      };
      const a = luminance(style.color),
        b = luminance(style.backgroundColor);
      return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    });
    expect(ratio).toBeGreaterThan(4.5);
    await page.keyboard.press("Escape");
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Appearance", exact: true }).click();
  await page.getByRole("radio", { name: "System", exact: true }).check();
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  expect(errors).toEqual([]);
});
