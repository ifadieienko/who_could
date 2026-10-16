export async function awaitSelect(control, value) {
  await control.click();
  const page = control.page();
  const option =
    typeof value === "object"
      ? page.getByRole("option", { name: value.label, exact: true })
      : page
          .getByRole("option")
          .and(
            page.locator("[data-value=" + JSON.stringify(String(value)) + "]"),
          );
  await option.click();
}
