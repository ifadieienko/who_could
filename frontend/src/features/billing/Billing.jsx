import { Button, ErrorBox, useAction } from "../../components/workshop/ui.jsx";
import { call } from "../../repair-api.js";
import { label } from "../forms/editor-options.js";
import { useEffect, useState } from "react";

export function Billing() {
  const [data, setData] = useState(null),
    [mail, setMail] = useState([]),
    [selectedPlan, setSelectedPlan] = useState("starter");
  const a = useAction();
  useEffect(() => {
    a.run(async () => {
      setData(await call("/v2/billing"));
      const workshops = await call("/v2/workshops");
      const wid = Number(localStorage.getItem("workshop"));
      if (
        workshops
          .find((w) => w.id === wid)
          ?.permissions.includes("contacts.read")
      )
        setMail(await call("/v2/outbox"));
    });
  }, []);
  const open = (path) =>
    a.run(async () => {
      const r = await call("/v2/billing/" + path, {
        method: "POST",
        ...(path === "checkout" ? { body: { plan: selectedPlan } } : {}),
      });
      location.href = r.url;
    });
  return (
    <>
      <h1>Подписка и уведомления</h1>
      <ErrorBox error={a.error} />
      {data && (
        <section className="w-panel">
          <h2>
            {data.writable
              ? "Рабочий доступ открыт"
              : "Режим чтения и экспорта"}
          </h2>
          <p>
            Тариф: {data.limits.name} · Состояние: {data.status}
          </p>
          <table className="w-table">
            <thead>
              <tr>
                <th>Ресурс</th>
                <th>Использовано</th>
                <th>Лимит</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Активные сотрудники, включая владельца</td>
                <td>{data.usage.members}</td>
                <td>{data.limits.members}</td>
              </tr>
              <tr>
                <td>Открытые заказы</td>
                <td>{data.usage.open_orders}</td>
                <td>{data.limits.open_orders}</td>
              </tr>
              <tr>
                <td>Фотографии, МБ</td>
                <td>{(data.usage.storage_bytes / 1024 ** 2).toFixed(1)}</td>
                <td>{data.limits.storage_bytes / 1024 ** 2}</td>
              </tr>
            </tbody>
          </table>
          <p className="w-muted">
            Закрытые заказы и отключённые сотрудники сохраняются в истории и не
            занимают активные места. Стоимость и период оплаты указаны в Stripe
            перед подтверждением.
          </p>
          <p>
            Пробный период до: {data.trial_until || "—"}
            <br />
            Оплаченный период до: {data.paid_until || "—"}
          </p>
          {data.configured ? (
            <div className="w-actions">
              {!data.has_subscription && (
                <>
                  <select
                    aria-label="Тариф подписки"
                    value={selectedPlan}
                    onChange={(e) => setSelectedPlan(e.target.value)}
                  >
                    {data.plans.map((p) => (
                      <option
                        key={p.code}
                        value={p.code}
                        disabled={!p.available}
                      >
                        {p.name} · {p.members} сотрудников · {p.open_orders}{" "}
                        заказов
                      </option>
                    ))}
                  </select>
                  <Button
                    disabled={
                      !data.plans.find((p) => p.code === selectedPlan)
                        ?.available || a.busy
                    }
                    onClick={() => open("checkout")}
                  >
                    Оформить подписку
                  </Button>
                </>
              )}
              <Button secondary onClick={() => open("portal")}>
                Управлять подпиской
              </Button>
            </div>
          ) : (
            <p>
              Онлайн-оплата пока недоступна. Обратитесь к администратору
              сервиса.
            </p>
          )}
        </section>
      )}
      <section className="w-panel">
        <h2>Доставка сообщений</h2>
        {mail.length ? (
          mail.map((m) => (
            <p key={m.id}>
              {m.subject} · {m.status} · попыток: {m.attempts}
              {m.last_error && " · " + m.last_error}
            </p>
          ))
        ) : (
          <p>Сообщений пока нет.</p>
        )}
      </section>
    </>
  );
}
