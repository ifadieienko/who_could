import {
  Button,
  ErrorBox,
  Field,
  useAction,
} from "../../components/workshop/ui.jsx";
import { call } from "../../repair-api.js";
import { label } from "../forms/editor-options.js";
import { money, statusNames, time } from "../../app/format.js";
import { useState } from "react";

export function Finance({ order: o, can, onUpdate }) {
  const [lines, setLines] = useState([
      { description: "", quantity: 1, unit_cents: 0 },
    ]),
    [link, setLink] = useState(""),
    [amount, setAmount] = useState(""),
    [method, setMethod] = useState("cash");
  const a = useAction();
  const edit = (i, key, value) =>
    setLines(lines.map((x, n) => (n === i ? { ...x, [key]: value } : x)));
  return (
    <div className="w-order-layout">
      <section className="w-panel">
        <h2>Сметы и согласования</h2>
        <ErrorBox error={a.error} />
        {o.estimates?.map((q) => (
          <article className="w-estimate" key={q.id}>
            <h3>
              Версия {q.revision} · {money(q.total_cents)}{" "}
              <span className="w-tag">{statusNames[q.status]}</span>
            </h3>
            {q.lines.map((l, i) => (
              <p key={i}>
                {l.description} × {l.quantity} —{" "}
                {money(l.quantity * l.unit_cents)}
              </p>
            ))}
            {q.decision_name && (
              <small>
                {q.decision_name} · {time(q.decision_at)}
              </small>
            )}
          </article>
        ))}
        {can("finance.write") &&
          !["draft", "issued", "cancelled"].includes(o.status) && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                a.run(async () => {
                  const r = await call("/v2/orders/" + o.id + "/estimates", {
                    method: "POST",
                    body: { version: o.version, lines },
                  });
                  onUpdate(r.order);
                  setLink(location.origin + r.approval_path);
                });
              }}
            >
              <h3>Новая версия сметы</h3>
              {lines.map((l, i) => (
                <div className="w-line" key={i}>
                  <input
                    aria-label="Работа или деталь"
                    placeholder="Работа / деталь"
                    required
                    value={l.description}
                    onChange={(e) => edit(i, "description", e.target.value)}
                  />
                  <input
                    aria-label="Количество"
                    type="number"
                    min="1"
                    required
                    value={l.quantity}
                    onChange={(e) =>
                      edit(i, "quantity", Number(e.target.value))
                    }
                  />
                  <input
                    aria-label="Цена PLN"
                    type="number"
                    min="0"
                    step="0.01"
                    required
                    value={l.unit_cents / 100}
                    onChange={(e) =>
                      edit(
                        i,
                        "unit_cents",
                        Math.round(Number(e.target.value) * 100),
                      )
                    }
                  />
                  <button
                    type="button"
                    aria-label="Удалить строку"
                    disabled={lines.length === 1}
                    onClick={() => setLines(lines.filter((_, n) => n !== i))}
                  >
                    ×
                  </button>
                </div>
              ))}
              <div className="w-actions">
                <Button
                  type="button"
                  secondary
                  onClick={() =>
                    setLines([
                      ...lines,
                      { description: "", quantity: 1, unit_cents: 0 },
                    ])
                  }
                >
                  + Строка
                </Button>
                <Button disabled={a.busy}>Создать и получить ссылку</Button>
              </div>
            </form>
          )}
        {link && (
          <div className="w-notice">
            <p>Ссылка для клиента. Скопируйте её сейчас:</p>
            <input
              aria-label="Ссылка согласования"
              readOnly
              value={link}
              onFocus={(e) => e.target.select()}
            />
            <a href={link} target="_blank" rel="noreferrer">
              Открыть страницу клиента
            </a>
          </div>
        )}
      </section>
      <section className="w-panel">
        <h2>Оплата</h2>
        <h3>Получено: {money(o.paid_cents)}</h3>
        {o.payments?.map((p) => (
          <p key={p.id}>
            {money(p.amount_cents)} · {p.method} · {time(p.created_at)}
          </p>
        ))}
        {can("finance.write") && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              a.run(async () => {
                onUpdate(
                  await call("/v2/orders/" + o.id + "/payments", {
                    method: "POST",
                    body: {
                      version: o.version,
                      amount_cents: Math.round(Number(amount) * 100),
                      method,
                    },
                  }),
                );
                setAmount("");
              });
            }}
          >
            <Field label="Сумма PLN">
              <input
                type="number"
                min="0.01"
                step="0.01"
                required
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </Field>
            <Field label="Способ">
              <select
                value={method}
                onChange={(e) => setMethod(e.target.value)}
              >
                <option value="cash">Наличные</option>
                <option value="card">Карта</option>
                <option value="transfer">Перевод</option>
                <option value="other">Другой</option>
              </select>
            </Field>
            <Button disabled={a.busy}>Записать полученную оплату</Button>
          </form>
        )}
        <p className="w-muted">
          Запись оплаты фиксирует полученную сумму. Она не списывает деньги и не
          заменяет фискальный документ.
        </p>
      </section>
    </div>
  );
}
