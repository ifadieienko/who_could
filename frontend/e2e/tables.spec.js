import { test, expect } from "@playwright/test";
import { awaitSelect } from "./select.js";

test("table editor, repeating rows, persistence, mobile and closed-job controls", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await awaitSelect(
    page.getByRole("combobox", { name: "Language / Язык / Język" }),
    "en",
  );
  await page.getByRole("button", { name: "New workshop", exact: true }).click();
  await page.getByLabel("Your name").fill("Tables owner");
  await page.getByLabel("Workshop name").fill("Tables demo");
  await page.getByLabel("Email", { exact: true }).fill("tables-ui@example.com");
  await page
    .getByLabel("Password", { exact: true })
    .fill("browser-password-123");
  await page.getByRole("button", { name: "Get started" }).click();
  await page.getByRole("button", { name: "Forms", exact: true }).click();
  await page.getByLabel("Название формы", { exact: true }).fill("Table sheet");
  await page
    .getByLabel("Назначение формы", { exact: true })
    .fill("measurement");
  const field = page.locator(".w-field-editor").first();
  await field.getByLabel("Название", { exact: true }).fill("Readings");
  await awaitSelect(field.getByLabel("Тип", { exact: true }), "table");
  await field.getByLabel("Maximum rows").fill("3");
  await field.getByLabel("Minimum rows").fill("1");
  const first = field.locator(".w-table-column").first();
  await first.getByLabel("Column name").fill("Reading");
  await first.getByLabel("Unit", { exact: true }).fill("mm");
  await first.getByLabel("Decimal places").fill("2");
  await first.getByLabel("Required on completion").check();
  await field.getByRole("button", { name: "Add column" }).click();
  const second = field.locator(".w-table-column").nth(1);
  await second.getByLabel("Column name").fill("Result");
  await awaitSelect(second.getByLabel("Column type"), "select");
  await second.getByLabel("Options — one per line").fill("Pass\nFail");
  await second.getByLabel("Required on completion").check();
  const saved = page.waitForResponse(
    (r) => r.url().endsWith("/v2/templates") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Сохранить черновик", exact: true })
    .click();
  const response = await saved;
  expect(response.ok(), await response.text()).toBeTruthy();
  const template = await response.json();
  await page
    .getByRole("button", { name: "Опубликовать сохранённую версию" })
    .click();
  await expect(
    page.getByText("Опубликованная версия неизменяема.", { exact: false }),
  ).toBeVisible();
  const headers = {
    "X-Workshop-Id": await page.evaluate(() =>
      localStorage.getItem("workshop"),
    ),
    Origin: new URL(page.url()).origin,
  };
  async function post(path, data) {
    const result = await page.request.post("/api/v2/" + path, {
      headers,
      data,
    });
    expect(result.ok(), await result.text()).toBeTruthy();
    return result.json();
  }
  const templates = await (
    await page.request.get("/api/v2/templates", { headers })
  ).json();
  const intake = templates.find((t) => t.purpose === "intake" && t.published);
  const workflow = await post("workflows", {
    name: "Table process",
    stages: [
      {
        key: "measure",
        name: "Measure",
        form_phase: "measurement",
        next: ["ready"],
      },
      { key: "ready", name: "Ready", category: "ready" },
    ],
  });
  const job = await post("orders", {
    template_id: intake.id,
    workflow_id: workflow.id,
    customer: { name: "Table customer" },
    model: "Gauge",
    problem: "Inspect",
    stage_forms: { measurement: template.id },
    draft: false,
  });
  await page.goto("/orders/" + job.id);
  await page.getByRole("button", { name: "Table sheet", exact: true }).click();
  const table = page.locator(".w-form-table");
  await table.getByRole("button", { name: "Add row" }).click();
  await page.getByLabel("Reading · Row 1", { exact: true }).fill("1.25");
  await awaitSelect(page.getByLabel("Result · Row 1", { exact: true }), "Pass");
  await table.getByRole("button", { name: "Add row" }).click();
  await page.getByLabel("Reading · Row 2", { exact: true }).fill("0");
  await awaitSelect(page.getByLabel("Result · Row 2", { exact: true }), "Fail");
  await table.getByRole("button", { name: "Add row" }).click();
  await expect(table.getByRole("button", { name: "Add row" })).toBeDisabled();
  await table
    .getByRole("button", { name: "Remove row 3", exact: true })
    .click();
  const persisted = page.waitForResponse(
    (r) =>
      r.url().endsWith("/forms/measurement") &&
      r.request().method() === "PATCH",
  );
  await page
    .getByRole("button", { name: "Сохранить форму", exact: true })
    .click();
  expect((await persisted).ok()).toBeTruthy();
  await page.reload();
  await page.getByRole("button", { name: "Table sheet", exact: true }).click();
  await expect(page.getByLabel("Reading · Row 1", { exact: true })).toHaveValue(
    "1.25",
  );
  await expect(page.getByLabel("Reading · Row 2", { exact: true })).toHaveValue(
    "0",
  );
  await expect(
    page.getByLabel("Result · Row 2", { exact: true }),
  ).toHaveAttribute("data-value", "Fail");
  await table
    .getByRole("button", { name: "Remove row 1", exact: true })
    .click();
  await expect(page.getByLabel("Reading · Row 1", { exact: true })).toHaveValue(
    "0",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  const region = table.getByRole("region", { name: "Readings" });
  const box = await region.boundingBox();
  expect(box.width).toBeLessThan(390);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBeTruthy();
  // Closing the job disables inherited fieldset controls, including row actions.
  const current = await (
    await page.request.get("/api/v2/orders/" + job.id, { headers })
  ).json();
  await post("orders/" + job.id + "/cancel", {
    version: current.version,
    reason: "Browser test finished",
  });
  await page.reload();
  await page.getByRole("button", { name: "Table sheet", exact: true }).click();
  await expect(table.getByRole("button", { name: "Add row" })).toBeDisabled();
  await expect(
    page.getByLabel("Reading · Row 1", { exact: true }),
  ).toBeDisabled();
  expect(errors).toEqual([]);
});
