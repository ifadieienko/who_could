import { test, expect } from "@playwright/test";

test("asset job creation, site pagination, editing and stale-version protection", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByRole("button", { name: "Новая мастерская" }).click();
  await page.getByLabel("Ваше имя", { exact: true }).fill("Job owner");
  await page.getByLabel("Название мастерской").fill("Job demo");
  await page
    .getByLabel("Email", { exact: true })
    .fill("generic-ui@example.com");
  await page.getByLabel("Пароль", { exact: true }).fill("browser-password-123");
  await page.getByRole("button", { name: "Начать работу" }).click();
  await expect(
    page.getByRole("button", { name: "New job for an asset" }),
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
  const sheet = await post("templates", {
    name: "Measurement sheet",
    purpose: "history",
    fields: [
      {
        key: "reading",
        label: "Instrument reading",
        type: "number",
        required: true,
      },
    ],
  });
  await post(`templates/${sheet.id}/publish`);
  const workflow = await post("workflows", {
    name: "Instrument inspection",
    stages: [
      {
        key: "inspect",
        name: "Inspect",
        form_phase: "history",
        next: ["ready"],
      },
      { key: "ready", name: "Ready", category: "ready" },
    ],
  });
  const customer = await post("customer-records", { name: "Job customer" });
  const other = await post("customer-records", { name: "Other customer" });
  const asset = await post("assets", {
    customer_id: customer.id,
    name: "Gauge without model",
    asset_type: "instrument",
  });
  let site;
  for (let i = 1; i <= 31; i++)
    site = await post("sites", { customer_id: customer.id, name: `Site ${i}` });
  await page.getByRole("button", { name: "New job for an asset" }).click();
  await page
    .getByLabel("Customer", { exact: true })
    .selectOption(String(customer.id));
  await page
    .getByLabel("Asset", { exact: true })
    .selectOption(String(asset.id));
  await page.getByRole("button", { name: "More sites" }).click();
  await page.getByLabel("Customer site").selectOption(String(site.id));
  await page
    .getByLabel("Customer", { exact: true })
    .selectOption(String(other.id));
  await expect(page.getByLabel("Asset", { exact: true })).toHaveValue("");
  await expect(page.getByLabel("Customer site")).toHaveValue("");
  await expect(
    page.getByRole("button", { name: "Create job draft" }),
  ).toBeDisabled();
  await page
    .getByLabel("Customer", { exact: true })
    .selectOption(String(customer.id));
  await page
    .getByLabel("Asset", { exact: true })
    .selectOption(String(asset.id));
  await page.getByRole("button", { name: "More sites" }).click();
  await page.getByLabel("Customer site").selectOption(String(site.id));
  await page
    .getByLabel("Workflow", { exact: true })
    .selectOption(String(workflow.id));
  await page.getByLabel("Stage form: history").selectOption(String(sheet.id));
  await page.getByLabel("Job type").selectOption("inspection");
  await page.getByLabel("Priority", { exact: true }).selectOption("high");
  await page.getByLabel("Work description").fill("Inspect the gauge");
  await page.getByRole("button", { name: "Create job draft" }).click();
  await expect(
    page.getByRole("heading", { name: /Gauge without model/ }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Measurement sheet", exact: true })
    .click();
  await page.getByLabel("Instrument reading").fill("12.5");
  await page
    .getByRole("button", { name: "Сохранить форму", exact: true })
    .click();
  await page.getByRole("button", { name: "История", exact: true }).click();
  await expect(page.getByLabel("Instrument reading")).toHaveCount(0);
  await page
    .getByRole("button", { name: "Measurement sheet", exact: true })
    .click();
  await expect(page.getByLabel("Instrument reading")).toHaveValue("12.5");
  const path = new URL(page.url()).pathname;
  const id = path.split("/").pop();
  await expect(page.getByLabel("Job type")).toHaveValue("Inspection");
  await expect(page.getByLabel("Customer site")).toHaveValue(String(site.id));
  await page.getByLabel("Priority", { exact: true }).selectOption("urgent");
  await page.getByLabel("Customer site").selectOption("");
  await page.getByRole("button", { name: "Save job settings" }).click();
  await expect(page.getByLabel("Priority", { exact: true })).toHaveValue(
    "urgent",
  );
  await page.reload();
  await expect(page.getByLabel("Priority", { exact: true })).toHaveValue(
    "urgent",
  );
  await expect(page.getByLabel("Customer site")).toHaveValue("");
  const current = await (
    await page.request.get("/api/v2/jobs/" + id, { headers })
  ).json();
  const changed = await page.request.patch("/api/v2/jobs/" + id, {
    headers,
    data: { version: current.version, priority: "low" },
  });
  expect(changed.ok()).toBeTruthy();
  await page.getByLabel("Priority", { exact: true }).selectOption("normal");
  await page.getByRole("button", { name: "Save job settings" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Заказ изменён другим сотрудником",
  );
  await page.getByRole("button", { name: "Обновить", exact: true }).click();
  await expect(page.getByLabel("Priority", { exact: true })).toHaveValue("low");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("button", { name: "Save job settings" }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
