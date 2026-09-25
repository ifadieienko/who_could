import {
  Button,
  ErrorBox,
  Field,
  useAction,
} from "../../components/workshop/ui.jsx";
import { call } from "../../repair-api.js";
import { go } from "../../app/navigation.js";
import { label } from "../forms/editor-options.js";
import { useEffect, useState } from "react";

export function NewOrder() {
  const [templates, setTemplates] = useState([]),
    [flows, setFlows] = useState([]),
    [customers, setCustomers] = useState([]),
    [devices, setDevices] = useState([]);
  const [form, setForm] = useState({
    stage_forms: {},
    template_id: "",
    workflow_id: "",
    customer_id: "",
    device_id: "",
    customer: { name: "", email: "", phone: "" },
    model: "",
    serial: "",
    problem: "",
    condition: "",
    accessories: "",
    location: "",
  });
  const a = useAction();
  useEffect(() => {
    a.run(async () => {
      const [t, w] = await Promise.all([
        call("/v2/templates"),
        call("/v2/workflows"),
      ]);
      setTemplates(t.filter((x) => x.published));
      setFlows(w);
      setForm((f) => ({
        ...f,
        template_id:
          t.find((x) => x.published && x.purpose === "intake")?.id || "",
        workflow_id: w[0]?.id || "",
      }));
    });
  }, []);
  const update = (key, value) => setForm((f) => ({ ...f, [key]: value }));
  return (
    <>
      <header className="w-page-head">
        <div>
          <p className="w-eyebrow">Приём техники</p>
          <h1>Новый заказ</h1>
        </div>
        <Button secondary onClick={() => go("/orders")}>
          Отмена
        </Button>
      </header>
      <form
        className="w-panel"
        onSubmit={(e) => {
          e.preventDefault();
          a.run(async () => {
            const body = {
              ...form,
              template_id: Number(form.template_id),
              workflow_id: Number(form.workflow_id),
              customer_id: Number(form.customer_id) || null,
              device_id: Number(form.device_id) || null,
              customer: form.customer_id
                ? null
                : { ...form.customer, email: form.customer.email || null },
              draft: true,
            };
            const order = await call("/v2/orders", { method: "POST", body });
            go("/orders/" + order.id);
          });
        }}
      >
        <ErrorBox error={a.error} />
        <div className="w-grid">
          <Field label="Форма приёма">
            <select
              required
              value={form.template_id}
              onChange={(e) => update("template_id", e.target.value)}
            >
              {templates
                .filter((t) => t.purpose === "intake")
                .map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} · v{t.revision}
                  </option>
                ))}
            </select>
          </Field>
          <Field label="Процесс ремонта">
            <select
              required
              value={form.workflow_id}
              onChange={(e) => update("workflow_id", e.target.value)}
            >
              {flows.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name} · v{w.revision}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <div className="w-grid three">
          {[
            ["diagnosis", "Форма диагностики"],
            ["repair", "Форма ремонта"],
            ["quality", "Форма проверки"],
          ].map(([phase, title]) => (
            <Field key={phase} label={title}>
              <select
                value={form.stage_forms[phase] || ""}
                onChange={(e) => {
                  const selected = { ...form.stage_forms };
                  if (e.target.value) selected[phase] = Number(e.target.value);
                  else delete selected[phase];
                  update("stage_forms", selected);
                }}
                required={flows
                  .find((w) => w.id === Number(form.workflow_id))
                  ?.stages.some((s) => s.form_phase === phase)}
              >
                <option value="">Не назначена</option>
                {templates
                  .filter((t) => t.purpose === phase)
                  .map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name} · v{t.revision}
                    </option>
                  ))}
              </select>
            </Field>
          ))}
        </div>
        <p className="w-muted">
          Выбранные версии форм закрепятся за заказом. Процесс может требовать
          заполнить форму перед выходом с этапа.
        </p>
        <h2>Клиент</h2>
        <div className="w-toolbar">
          <input
            aria-label="Поиск клиента"
            placeholder="Найти по имени, email или телефону"
            onChange={(e) =>
              a.run(async () =>
                setCustomers(
                  await call(
                    "/v2/customers?q=" + encodeURIComponent(e.target.value),
                  ),
                ),
              )
            }
          />
          <select
            aria-label="Существующий клиент"
            value={form.customer_id}
            onChange={(e) => {
              update("customer_id", e.target.value);
              update("device_id", "");
              a.run(async () =>
                setDevices(
                  e.target.value
                    ? await call("/v2/devices?customer_id=" + e.target.value)
                    : [],
                ),
              );
            }}
          >
            <option value="">Новый клиент</option>
            {customers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} · {c.phone}
              </option>
            ))}
          </select>
        </div>
        {!form.customer_id && (
          <div className="w-grid three">
            {[
              ["name", "Имя"],
              ["phone", "Телефон"],
              ["email", "Email"],
            ].map(([key, name]) => (
              <Field key={key} label={name}>
                <input
                  required={key === "name"}
                  type={key === "email" ? "email" : "text"}
                  value={form.customer[key]}
                  onChange={(e) =>
                    update("customer", {
                      ...form.customer,
                      [key]: e.target.value,
                    })
                  }
                />
              </Field>
            ))}
          </div>
        )}
        <h2>Устройство</h2>
        {devices.length > 0 && (
          <Field label="Устройство из истории">
            <select
              value={form.device_id}
              onChange={(e) => update("device_id", e.target.value)}
            >
              <option value="">Новое устройство</option>
              {devices.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.model} · {d.serial}
                </option>
              ))}
            </select>
          </Field>
        )}
        <div className="w-grid">
          {!form.device_id &&
            [
              ["model", "Модель"],
              ["serial", "Серийный номер"],
            ].map(([key, name]) => (
              <Field key={key} label={name}>
                <input
                  required={key === "model"}
                  value={form[key]}
                  onChange={(e) => update(key, e.target.value)}
                />
              </Field>
            ))}
          <Field label="Полка / ячейка">
            <input
              value={form.location}
              onChange={(e) => update("location", e.target.value)}
            />
          </Field>
        </div>
        {[
          ["problem", "Заявленная неисправность"],
          ["condition", "Состояние корпуса / повреждения"],
          ["accessories", "Комплектность"],
        ].map(([key, name]) => (
          <Field key={key} label={name}>
            <textarea
              required={key === "problem"}
              value={form[key]}
              onChange={(e) => update(key, e.target.value)}
            />
          </Field>
        ))}
        <p className="w-muted">
          После создания добавьте фотографии и заполните поля формы, затем
          подтвердите приём.
        </p>
        <Button disabled={a.busy || !form.template_id || !form.workflow_id}>
          Создать черновик приёмки
        </Button>
      </form>
    </>
  );
}
