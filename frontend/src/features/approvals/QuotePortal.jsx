import {
  Button,
  ErrorBox,
  Field,
  useAction,
} from "../../components/workshop/ui.jsx";
import { call } from "../../repair-api.js";
import { label } from "../forms/editor-options.js";
import { money, statusNames, time } from "../../app/format.js";
import { useEffect, useState } from "react";

export function QuotePortal({ token }) {
  const [q, setQuote] = useState(null),
    [name, setName] = useState(""),
    [confirmed, setConfirmed] = useState(false);
  const a = useAction();
  useEffect(() => {
    a.run(async () => setQuote(await call("/public/quotes/" + token)));
  }, [token]);
  const decide = (decision) =>
    a.run(async () => {
      await call("/public/quotes/" + token, {
        method: "POST",
        body: { name, confirmed, decision },
      });
      setQuote(await call("/public/quotes/" + token));
    });
  return (
    <div className="w-public">
      <section className="w-panel">
        <p className="w-eyebrow">Согласование ремонта</p>
        <ErrorBox error={a.error} />
        {q && (
          <>
            <h1>{q.workshop}</h1>
            <p>
              Заказ #{q.number} · Смета №{q.revision}
            </p>
            {q.lines.map((l, i) => (
              <p key={i}>
                {l.description} × {l.quantity} —{" "}
                {money(l.quantity * l.unit_cents)}
              </p>
            ))}
            <h2>Итого: {money(q.total_cents)}</h2>
            <p>Действует до {time(q.expires_at)}</p>
            {q.status === "pending" ? (
              <>
                <Field label="Ваше имя">
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                </Field>
                <label className="w-check">
                  <input
                    type="checkbox"
                    checked={confirmed}
                    onChange={(e) => setConfirmed(e.target.checked)}
                  />
                  Я ознакомился с этой версией сметы и подтверждаю своё решение.
                </label>
                <div className="w-actions">
                  <Button
                    disabled={a.busy || !confirmed || name.length < 2}
                    onClick={() => decide("accepted")}
                  >
                    Согласовать стоимость
                  </Button>
                  <Button
                    secondary
                    disabled={a.busy || !confirmed || name.length < 2}
                    onClick={() => decide("declined")}
                  >
                    Отказаться
                  </Button>
                </div>
              </>
            ) : (
              <div className="w-notice">
                Решение зарегистрировано: {statusNames[q.status]}
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
