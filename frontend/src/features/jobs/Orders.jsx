import { Button, ErrorBox, useAction } from "../../components/workshop/ui.jsx";
import { call } from "../../repair-api.js";
import { empty, label } from "../forms/editor-options.js";
import { go } from "../../app/navigation.js";
import { statusNames, time } from "../../app/format.js";
import { useEffect, useState } from "react";

export function Orders({ can }) {
  const [data, setData] = useState({ items: [], total: 0 }),
    [query, setQuery] = useState(""),
    [status, setStatus] = useState(""),
    [stalled, setStalled] = useState(false),
    [page, setPage] = useState(1);
  const a = useAction();
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      call(
        `/v2/orders?${new URLSearchParams({ q: query, status, stalled, page })}`,
        { signal: controller.signal },
      )
        .then(setData)
        .catch((e) => {
          if (e.name !== "AbortError") a.setError(e.message);
        });
    }, 200);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [query, status, stalled, page]);
  return (
    <>
      <header className="w-page-head">
        <div>
          <p className="w-eyebrow">Рабочая очередь</p>
          <h1>
            Заказы <span>{data.total}</span>
          </h1>
        </div>
        {can("orders.create") && (
          <Button onClick={() => go("/orders/new")}>
            + Принять устройство
          </Button>
        )}
      </header>
      <div className="w-toolbar">
        <input
          aria-label="Поиск заказов"
          placeholder="Номер, модель, S/N, неисправность, полка…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(1);
          }}
        />
        <select
          aria-label="Статус"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
          }}
        >
          <option value="">Все состояния</option>
          {["draft", "active", "waiting", "ready", "issued", "cancelled"].map(
            (k) => (
              <option key={k} value={k}>
                {statusNames[k]}
              </option>
            ),
          )}
        </select>
        <label className="w-check">
          <input
            type="checkbox"
            checked={stalled}
            onChange={(e) => {
              setStalled(e.target.checked);
              setPage(1);
            }}
          />
          Требуют внимания
        </label>
      </div>
      <ErrorBox error={a.error} />
      <div className="w-table-wrap">
        <table className="w-table">
          <thead>
            <tr>
              <th>Заказ / устройство</th>
              <th>Неисправность</th>
              <th>Этап</th>
              <th>Хранение</th>
              <th>Обновлён</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((o) => (
              <tr key={o.id} onClick={() => go("/orders/" + o.id)}>
                <td>
                  <button
                    className="w-link"
                    onClick={(e) => {
                      e.stopPropagation();
                      go("/orders/" + o.id);
                    }}
                  >
                    #{o.number} · {o.model}
                  </button>
                  <small>
                    {o.serial}
                    {o.warranty_of && " · Гарантийный возврат"}
                  </small>
                </td>
                <td>{o.problem || "—"}</td>
                <td>
                  <span className={"w-tag " + o.status}>
                    {statusNames[o.status]}
                  </span>
                  <small>
                    {o.stage_name}
                    {o.stalled && " · Задержка"}
                  </small>
                </td>
                <td>{o.location || "Не указано"}</td>
                <td>{time(o.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!data.items.length && (
          <div className="w-empty">Заказов в этой выборке нет.</div>
        )}
      </div>
      <footer className="w-pagination">
        <Button
          secondary
          disabled={page === 1}
          onClick={() => setPage(page - 1)}
        >
          Назад
        </Button>
        <span>Страница {page}</span>
        <Button
          secondary
          disabled={page * 30 >= data.total}
          onClick={() => setPage(page + 1)}
        >
          Далее
        </Button>
      </footer>
    </>
  );
}
