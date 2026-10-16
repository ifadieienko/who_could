import { expect } from "@playwright/test";
export async function awaitSelect(control, value) {
  await control.click();
  await expect(control).toHaveAttribute("aria-expanded", "true");
  await expect(control).toHaveAttribute("aria-controls", /.+/);
  const page = control.page();
  const list = page.locator(
    "[id=" + JSON.stringify(await control.getAttribute("aria-controls")) + "]",
  );
  const option =
    typeof value === "object"
      ? list.getByRole("option", { name: value.label, exact: true })
      : list
          .getByRole("option")
          .and(
            page.locator("[data-value=" + JSON.stringify(String(value)) + "]"),
          );
  await option.click();
}
