import { test, expect } from "@playwright/test";
test("приём → фото → согласование → ремонт → проверка → оплата → выдача; мобильная QR-карточка", async ({
  page,
  browser,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByRole("button", { name: "Новая мастерская" }).click();
  await page.getByLabel("Ваше имя", { exact: true }).fill("Владелец");
  await page.getByLabel("Название мастерской").fill("Тестовая мастерская");
  await page.getByLabel("Email", { exact: true }).fill("browser@example.com");
  await page.getByLabel("Пароль", { exact: true }).fill("browser-password-123");
  await page.getByRole("button", { name: "Начать работу" }).click();
  await page.getByRole("button", { name: "+ Принять устройство" }).click();
  await page.getByLabel("Имя", { exact: true }).fill("Тестовый клиент");
  await page.getByLabel("Email", { exact: true }).fill("customer@example.com");
  await page.getByLabel("Модель", { exact: true }).fill("ThinkPad T14");
  await page.getByLabel("Серийный номер").fill("E2E-001");
  await page.getByLabel("Заявленная неисправность").fill("Не включается");
  await page.getByRole("button", { name: "Создать черновик приёмки" }).click();
  await expect(
    page.getByRole("heading", { name: /ThinkPad T14/ }),
  ).toBeVisible();
  const orderPath = new URL(page.url()).pathname;
  await page.getByRole("button", { name: "Фотографии", exact: true }).click();
  await page.getByLabel("Добавить фотографию").setInputFiles({
    name: "case.png",
    mimeType: "image/png",
    buffer: Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jR1sAAAAASUVORK5CYII=",
      "base64",
    ),
  });
  await expect(page.locator(".w-photos img")).toBeVisible();
  await page.getByRole("button", { name: "Карточка", exact: true }).click();
  await page
    .getByLabel("Диагностика · Диагностика", { exact: true })
    .fill("Неисправность питания");
  await page
    .getByLabel("Выполненные работы · Ремонт", { exact: true })
    .fill("Замена контроллера");
  await page
    .getByRole("button", { name: "Подтвердить приём", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Подтвердить приём", exact: true }),
  ).toHaveCount(0);
  async function transition(value) {
    await page.getByLabel("Перевести на этап").selectOption(value);
    await page.getByRole("button", { name: "Перевести", exact: true }).click();
    await expect(page.getByLabel("Перевести на этап")).toHaveValue("");
  }
  await transition("diagnosis");
  await page
    .getByRole("button", { name: "Сметы и оплата", exact: true })
    .click();
  await page.getByLabel("Работа или деталь").fill("Замена контроллера");
  await page.getByLabel("Цена PLN", { exact: true }).fill("120");
  await page.getByRole("button", { name: "Создать и получить ссылку" }).click();
  const quote = await page.getByLabel("Ссылка согласования").inputValue();
  const context = await browser.newContext();
  const client = await context.newPage();
  await client.goto(quote);
  await client.getByLabel("Ваше имя").fill("Тестовый клиент");
  await client.getByRole("checkbox").check();
  await client.getByRole("button", { name: "Согласовать стоимость" }).click();
  await expect(
    client.getByText("Решение зарегистрировано: Принята"),
  ).toBeVisible();
  await context.close();
  await page.getByRole("button", { name: "Обновить", exact: true }).click();
  await page.getByRole("button", { name: "Карточка", exact: true }).click();
  await transition("repair");
  await transition("quality");
  await page.getByLabel("Перевести на этап").selectOption("ready");
  for (const label of [
    "Комплектность проверена",
    "Неисправность устранена",
    "Финальный тест пройден",
  ])
    await page.getByLabel(label, { exact: true }).check();
  await page.getByRole("button", { name: "Перевести", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Выдать устройство" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Сметы и оплата", exact: true })
    .click();
  await page.getByLabel("Сумма PLN").fill("120");
  await page
    .getByRole("button", { name: "Записать полученную оплату" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Получено: 120.00 PLN" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Карточка", exact: true }).click();
  await page.getByLabel("Получатель", { exact: true }).fill("Тестовый клиент");
  await page.getByRole("button", { name: "Подтвердить выдачу" }).click();
  await expect(page.locator(".w-page-head .w-tag")).toHaveText("Выдан");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(orderPath + "?workshop=1");
  await expect(
    page.getByRole("heading", { name: /ThinkPad T14/ }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.getByRole("button", { name: "QR-этикетка" }).click();
  await expect(page.locator("iframe")).toHaveCount(1);
  expect(await page.locator("iframe").getAttribute("srcdoc")).toContain("<svg");
  expect(errors).toEqual([]);
});
test("версии формы, сетка и многострочные проверки процесса", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Новая мастерская" }).click();
  await page.getByLabel("Ваше имя", { exact: true }).fill("Редактор");
  await page.getByLabel("Название мастерской").fill("Мастерская конструктора");
  await page.getByLabel("Email", { exact: true }).fill("editor@example.com");
  await page.getByLabel("Пароль", { exact: true }).fill("editor-password-123");
  await page.getByRole("button", { name: "Начать работу" }).click();
  await page.getByRole("button", { name: "Формы", exact: true }).click();
  await page.getByLabel("Название формы").fill("Ноутбуки");
  await page.getByLabel("Количество колонок").selectOption("3");
  await page.getByLabel("Название", { exact: true }).fill("Проверка питания");
  await page.getByLabel("Ширина в колонках").selectOption("2");
  await page.getByLabel("Строка (пусто — автоматически)").fill("2");
  await page.getByRole("button", { name: "Сохранить черновик" }).click();
  await page
    .getByRole("button", { name: "Опубликовать сохранённую версию" })
    .click();
  await expect(page.getByLabel("Название формы")).toBeDisabled();
  await page.getByRole("button", { name: "Создать следующую версию" }).click();
  await expect(page.getByLabel("Название формы")).toBeEnabled();
  await expect(page.getByLabel("Количество колонок")).toHaveValue("3");
  await expect(page.getByLabel("Строка (пусто — автоматически)")).toHaveValue(
    "2",
  );
  await page.getByRole("button", { name: "Процессы", exact: true }).click();
  const checks = page
    .getByLabel("Обязательные проверки — каждая с новой строки")
    .last();
  await checks.fill("Внешний осмотр");
  await checks.press("End");
  await checks.press("Enter");
  await checks.pressSequentially("Проверка заряда");
  await expect(checks).toHaveValue("Внешний осмотр\nПроверка заряда");
  await page.getByRole("button", { name: "Сохранить новую версию" }).click();
  await expect(
    page.getByRole("button", { name: "Стандартный ремонт · v2" }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByLabel("Обязательные проверки — каждая с новой строки").last(),
  ).toHaveValue("Внешний осмотр\nПроверка заряда");
  await page.screenshot({
    path: "test-results/workflow-desktop.png",
    fullPage: true,
  });
});

test("раздельные формы этапов, обязательность и обзор лимитов", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByRole("button", { name: "Новая мастерская" }).click();
  await page.getByLabel("Ваше имя", { exact: true }).fill("Владелец форм");
  await page.getByLabel("Название мастерской").fill("Формы этапов");
  await page
    .getByLabel("Email", { exact: true })
    .fill("stageforms@example.com");
  await page.getByLabel("Пароль", { exact: true }).fill("browser-password-123");
  await page.getByRole("button", { name: "Начать работу" }).click();
  await expect(
    page.getByRole("button", { name: "+ Принять устройство" }),
  ).toBeVisible();
  const wid = await page.evaluate(() => localStorage.getItem("workshop"));
  const headers = { "X-Workshop-Id": wid, Origin: new URL(page.url()).origin };
  const response = await page.request.post("/api/v2/workflows", {
    headers,
    data: {
      name: "Проверка отдельных форм",
      stages: [
        {
          key: "diagnosis",
          name: "Диагностика",
          form_phase: "diagnosis",
          next: ["repair"],
        },
        {
          key: "repair",
          name: "Ремонт",
          form_phase: "repair",
          next: ["quality"],
        },
        {
          key: "quality",
          name: "Проверка",
          form_phase: "quality",
          next: ["ready"],
        },
        { key: "ready", name: "Готов", category: "ready" },
      ],
    },
  });
  expect(response.status()).toBe(201);
  const flow = await response.json();
  await page.getByRole("button", { name: "+ Принять устройство" }).click();
  await page.getByLabel("Процесс ремонта").selectOption(String(flow.id));
  await page
    .getByLabel("Форма диагностики")
    .selectOption({ label: "Диагностика · v1" });
  await page.getByLabel("Форма ремонта").selectOption({ label: "Ремонт · v1" });
  await page
    .getByLabel("Форма проверки")
    .selectOption({ label: "Проверка качества · v1" });
  await page.getByLabel("Имя", { exact: true }).fill("Клиент");
  await page.getByLabel("Модель", { exact: true }).fill("Телефон с формами");
  await page.getByLabel("Заявленная неисправность").fill("Не заряжается");
  await page.getByRole("button", { name: "Создать черновик приёмки" }).click();
  await page
    .getByRole("button", { name: "Подтвердить приём", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Подтвердить приём", exact: true }),
  ).toHaveCount(0);
  for (const [tab, target] of [
    ["Диагностика", "repair"],
    ["Ремонт", "quality"],
    ["Проверка качества", "ready"],
  ]) {
    await page.getByLabel("Перевести на этап").selectOption(target);
    await page.getByRole("button", { name: "Перевести", exact: true }).click();
    await expect(
      page.getByText("Заполните: " + tab, { exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: tab, exact: true }).click();
    await page.locator(".w-dynamic textarea").fill("Завершено: " + tab);
    const saved = page.waitForResponse(
      (r) => r.url().includes("/forms/") && r.request().method() === "PATCH",
    );
    await page.getByRole("button", { name: "Сохранить форму" }).click();
    expect((await saved).status()).toBe(200);
    await page.getByRole("button", { name: "Карточка", exact: true }).click();
    await page.getByRole("button", { name: "Перевести", exact: true }).click();
    await expect(page.getByLabel("Перевести на этап")).toHaveValue("");
  }
  await expect(
    page.getByRole("heading", { name: "Выдать устройство" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Подписка", exact: true }).click();
  await expect(
    page.getByText("Тариф: Starter", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByText("Активные сотрудники, включая владельца"),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("organization currency, timezone and settings language persist", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Новая мастерская" }).click();
  await page.getByLabel("Ваше имя", { exact: true }).fill("Organization Owner");
  await page
    .getByLabel("Название мастерской")
    .fill("Organization settings demo");
  await page
    .getByLabel("Email", { exact: true })
    .fill("organization-browser@example.com");
  await page.getByLabel("Пароль", { exact: true }).fill("browser-password-123");
  await page.getByRole("button", { name: "Начать работу" }).click();
  await page.getByRole("button", { name: "Организация", exact: true }).click();
  await page.getByLabel("Default currency").selectOption("EUR");
  await page.getByLabel("Time zone").fill("Europe/London");
  await page.getByRole("button", { name: "Save settings" }).click();
  await page.reload();
  await expect(page.getByLabel("Default currency")).toHaveValue("EUR");
  await expect(page.getByLabel("Time zone")).toHaveValue("Europe/London");
  await page.getByLabel("Language").selectOption("pl");
  await page.getByRole("button", { name: "Zapisz ustawienia" }).click();
  await page.reload();
  await expect(page.getByLabel("Waluta domyślna")).toHaveValue("EUR");
});

test("company, site and generic asset with a mobile QR card", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Новая мастерская" }).click();
  await page.getByLabel("Ваше имя", { exact: true }).fill("Asset Owner");
  await page.getByLabel("Название мастерской").fill("Asset demo");
  await page
    .getByLabel("Email", { exact: true })
    .fill("assets-browser@example.com");
  await page.getByLabel("Пароль", { exact: true }).fill("browser-password-123");
  await page.getByRole("button", { name: "Начать работу" }).click();
  await page.getByRole("button", { name: "Customers", exact: true }).click();
  await page.getByRole("button", { name: "New customer", exact: true }).click();
  await page.getByLabel("Customer type").selectOption("company");
  await page.getByLabel("Name", { exact: true }).fill("Precision Lab");
  await page
    .getByLabel("Company name", { exact: true })
    .fill("Precision Lab Ltd");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Precision Lab", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Sites", exact: true }).click();
  await page.getByRole("button", { name: "New site", exact: true }).click();
  await page.getByLabel("Name", { exact: true }).fill("Laboratory A");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Laboratory A", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Assets", exact: true }).click();
  await page.getByRole("button", { name: "New asset", exact: true }).click();
  await expect(
    page.getByLabel("Customer", { exact: true }).locator("option"),
  ).toHaveCount(2);
  await page
    .getByLabel("Customer", { exact: true })
    .selectOption({ label: "Precision Lab · Precision Lab Ltd" });
  await expect(
    page.getByLabel("Site (optional)").locator("option"),
  ).toHaveCount(2);
  await page
    .getByLabel("Site (optional)")
    .selectOption({ label: "Laboratory A" });
  await page.getByLabel("Name", { exact: true }).fill("Gauge A");
  await page.getByLabel("Serial number").fill("G-001");
  await page.getByLabel("Asset type").selectOption("instrument");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Gauge A", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "New job", exact: true }).click();
  await page
    .getByLabel("Description", { exact: true })
    .fill("Annual gauge inspection");
  await page.getByLabel("Job type").selectOption("inspection");
  await page.getByLabel("Priority").selectOption("high");
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await expect(page.getByRole("heading", { name: /Gauge A/ })).toBeVisible();
  await expect(page.getByLabel("Неисправность", { exact: true })).toHaveValue(
    "Annual gauge inspection",
  );
  await page.goBack();
  await page.goBack();
  await expect(
    page.getByRole("heading", { name: "Gauge A", exact: true }),
  ).toBeVisible();
  const path = new URL(page.url()).pathname;
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(path);
  await expect(
    page.getByRole("heading", { name: "Gauge A", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Print QR label" }).click();
  await expect(page.locator("iframe")).toHaveCount(1);
  expect(await page.locator("iframe").getAttribute("srcdoc")).toContain("<svg");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
