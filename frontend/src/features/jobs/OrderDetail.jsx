import {
  Button,
  ErrorBox,
  Field,
  useAction,
} from "../../components/workshop/ui.jsx";
import { DynamicFields } from "../forms/DynamicFields.jsx";
import { Finance } from "./Finance.jsx";
import { Photo } from "../../components/workshop/Photo.jsx";
import { call, printDocument } from "../../repair-api.js";
import { go } from "../../app/navigation.js";
import { label } from "../forms/editor-options.js";
import { localInput, localToISO, statusNames, time } from "../../app/format.js";
import { useEffect, useState } from "react";

export function OrderDetail({ id, can, user }) {
  const [o, setOrder] = useState(null),
    [values, setValues] = useState({}),
    [stageValues, setStageValues] = useState({}),
    [meta, setMeta] = useState({}),
    [members, setMembers] = useState([]),
    [history, setHistory] = useState([]);
  const [target, setTarget] = useState(""),
    [checks, setChecks] = useState([]),
    [note, setNote] = useState(""),
    [reason, setReason] = useState(""),
    [phase, setPhase] = useState("repair"),
    [tab, setTab] = useState("work");
  const a = useAction();
  const put = (data) => {
    setOrder(data);
    setValues(data.values);
    setStageValues(
      Object.fromEntries(
        Object.entries(data.stage_forms || {}).map(([phase, form]) => [
          phase,
          form.values,
        ]),
      ),
    );
    setMeta({
      problem: data.problem,
      condition: data.condition,
      accessories: data.accessories,
      location: data.location,
      due_at: localInput(data.due_at),
    });
    setPhase(data.status === "draft" ? "intake" : "repair");
    return data;
  };
  const refresh = () =>
    a.run(async () => {
      const [data, m, h] = await Promise.all([
        call("/v2/orders/" + id),
        call("/v2/members"),
        call("/v2/orders/" + id + "/history"),
      ]);
      put(data);
      setMembers(m);
      setHistory(h);
    });
  useEffect(() => {
    refresh();
  }, [id]);
  const mutate = (suffix, body, method = "POST") =>
    a.run(async () =>
      put(
        await call("/v2/orders/" + id + suffix, {
          method,
          body: { version: o.version, ...body },
        }),
      ),
    );
  if (!o)
    return (
      <>
        <ErrorBox error={a.error} />
        <p>Загрузка заказа…</p>
      </>
    );
  const loadMore = (kind) =>
    a.run(async () => {
      const page = await call(
        "/v2/orders/" + id + "/" + kind + "?before=" + o[kind + "_next"],
      );
      setOrder((current) => ({
        ...current,
        [kind]: [
          ...current[kind],
          ...page.items.filter(
            (item) => !current[kind].some((old) => old.id === item.id),
          ),
        ],
        [kind + "_next"]: page.next,
      }));
    });
  const stage = o.workflow.find((x) => x.key === o.stage),
    next = o.workflow.filter((x) => stage?.next.includes(x.key)),
    selected = next.find((x) => x.key === target);
  const editable = !["issued", "cancelled"].includes(o.status),
    allChecks = selected?.checks || [];
  const save = () =>
    mutate(
      "",
      {
        values,
        ...meta,
        due_at: meta.due_at ? localToISO(meta.due_at) : null,
        reason,
      },
      "PATCH",
    );
  return (
    <>
      <header className="w-page-head">
        <div>
          <button className="w-link" onClick={() => go("/orders")}>
            ← Заказы
          </button>
          <h1>
            #{o.number} · {o.model}
          </h1>
          <p>
            <span className={"w-tag " + o.status}>{statusNames[o.status]}</span>{" "}
            {o.stage_name}{" "}
            {o.stalled && (
              <strong className="w-warning"> · Требует внимания</strong>
            )}
          </p>
        </div>
        <div className="w-actions">
          <Button
            secondary
            onClick={() =>
              a.run(() => printDocument("/v2/orders/" + id + "/label"))
            }
          >
            QR-этикетка
          </Button>
          {can("contacts.read") && o.status !== "draft" && (
            <Button
              secondary
              onClick={() =>
                a.run(() =>
                  printDocument(
                    "/v2/orders/" +
                      id +
                      "/document?kind=" +
                      (o.status === "issued" ? "issue" : "intake"),
                  ),
                )
              }
            >
              Печатать акт
            </Button>
          )}
          <Button secondary onClick={refresh}>
            Обновить
          </Button>
        </div>
      </header>
      <ErrorBox error={a.error} />
      <div className="w-order-summary">
        <div>
          <small>Клиент</small>
          <strong>{o.customer?.name || "Доступ ограничен"}</strong>
          <span>
            {o.customer?.phone} {o.customer?.email}
          </span>
        </div>
        <div>
          <small>Устройство / S/N</small>
          <strong>{o.model}</strong>
          <span>{o.serial || "—"}</span>
        </div>
        <div>
          <small>Исполнитель</small>
          {can("orders.assign") ? (
            <select
              disabled={a.busy || !editable}
              value={o.assigned_to || ""}
              onChange={(e) =>
                mutate("/assign", { user_id: Number(e.target.value) || null })
              }
            >
              <option value="">Не назначен</option>
              {members
                .filter((m) => m.active)
                .map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
            </select>
          ) : (
            <>
              <strong>
                {members.find((m) => m.id === o.assigned_to)?.name ||
                  "Не назначен"}
              </strong>
              {!o.assigned_to && can("orders.transition") && (
                <Button onClick={() => mutate("/assign", { user_id: user.id })}>
                  Взять в работу
                </Button>
              )}
            </>
          )}
        </div>
      </div>
      <div className="w-tabs">
        {[
          ["work", "Карточка"],
          ...Object.entries(o.stage_forms || {}).map(([phase, form]) => [
            phase,
            form.template.name,
          ]),
          ["photos", "Фотографии"],
          ...(can("finance.read") ? [["finance", "Сметы и оплата"]] : []),
          ["history", "История"],
        ].map(([k, title]) => (
          <button
            key={k}
            className={tab === k ? "active" : ""}
            onClick={() => setTab(k)}
          >
            {title}
          </button>
        ))}
      </div>
      {tab === "work" && (
        <div className="w-order-layout">
          <section className="w-panel">
            <h2>Приём и сопровождение</h2>
            {["problem", "condition", "accessories", "location"].map(
              (key, i) => (
                <Field
                  key={key}
                  label={
                    [
                      "Неисправность",
                      "Состояние",
                      "Комплектность",
                      "Полка / ячейка",
                    ][i]
                  }
                >
                  <input
                    disabled={!editable || !can("orders.edit")}
                    value={meta[key]}
                    onChange={(e) =>
                      setMeta({ ...meta, [key]: e.target.value })
                    }
                  />
                </Field>
              ),
            )}
            <Field label="Обещанный срок">
              <input
                type="datetime-local"
                disabled={!editable || !can("orders.edit")}
                value={meta.due_at}
                onChange={(e) => setMeta({ ...meta, due_at: e.target.value })}
              />
            </Field>
            <fieldset disabled={!editable || !can("orders.edit")}>
              <DynamicFields
                template={o.template}
                values={values}
                setValues={setValues}
                can={can}
                attachments={o.attachments}
              />
            </fieldset>
            {editable && can("orders.edit") && (
              <>
                <Field label="Причина исправления данных приёма">
                  <input
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    placeholder="Обязательно при исправлении принятого устройства"
                  />
                </Field>
                <Button disabled={a.busy} onClick={save}>
                  Сохранить изменения
                </Button>
              </>
            )}
          </section>
          <aside className="w-panel">
            <h2>Следующее действие</h2>
            {o.status === "draft" && can("orders.create") && (
              <>
                <p>
                  Заполните обязательные поля и добавьте фото состояния и
                  комплектности.
                </p>
                <Button
                  disabled={a.busy}
                  onClick={() =>
                    a.run(async () => {
                      const saved = await call("/v2/orders/" + id, {
                        method: "PATCH",
                        body: {
                          version: o.version,
                          values,
                          ...meta,
                          due_at: meta.due_at ? localToISO(meta.due_at) : null,
                          reason,
                        },
                      });
                      put(saved);
                      put(
                        await call("/v2/orders/" + id + "/accept", {
                          method: "POST",
                          body: { version: saved.version },
                        }),
                      );
                    })
                  }
                >
                  Подтвердить приём
                </Button>
              </>
            )}
            {editable && o.status !== "draft" && can("orders.transition") && (
              <>
                <Field label="Перевести на этап">
                  <select
                    value={target}
                    onChange={(e) => {
                      setTarget(e.target.value);
                      setChecks([]);
                    }}
                  >
                    <option value="">Выберите этап</option>
                    {next.map((x) => (
                      <option key={x.key} value={x.key}>
                        {x.name}
                      </option>
                    ))}
                  </select>
                </Field>
                {selected?.requires_quote && (
                  <p className="w-muted">
                    Требуется согласованная актуальная смета.
                  </p>
                )}
                {allChecks.map((x) => (
                  <label className="w-check" key={x}>
                    <input
                      type="checkbox"
                      checked={checks.includes(x)}
                      onChange={(e) =>
                        setChecks(
                          e.target.checked
                            ? [...checks, x]
                            : checks.filter((c) => c !== x),
                        )
                      }
                    />
                    {x}
                  </label>
                ))}
                <Button
                  disabled={a.busy || !target}
                  onClick={async () => {
                    if (await mutate("/transition", { target, checks })) {
                      setTarget("");
                      setChecks([]);
                    }
                  }}
                >
                  Перевести
                </Button>
              </>
            )}
            {o.status === "ready" && can("orders.issue") && (
              <IssueForm order={o} mutate={mutate} busy={a.busy} />
            )}
            {["ready", "issued", "cancelled"].includes(o.status) &&
              can("orders.reopen") && (
                <Button
                  secondary
                  onClick={() => {
                    const reason = prompt("Причина повторного открытия");
                    if (reason) mutate("/reopen", { reason });
                  }}
                >
                  Открыть повторно
                </Button>
              )}
            {editable && can("orders.reopen") && (
              <Button
                secondary
                onClick={() => {
                  const reason = prompt("Причина отмены");
                  if (reason) mutate("/cancel", { reason });
                }}
              >
                Отменить заказ
              </Button>
            )}
            {o.status === "issued" && can("orders.create") && (
              <Button
                onClick={() => {
                  const text = prompt("Причина гарантийного обращения");
                  if (text)
                    a.run(async () => {
                      const r = await call("/v2/orders/" + id + "/warranty", {
                        method: "POST",
                        body: { version: o.version, text },
                      });
                      go("/orders/" + r.id);
                    });
                }}
              >
                Гарантийное обращение
              </Button>
            )}
            <hr />
            <h3>История устройства</h3>
            {history.map((h) => (
              <button
                className="w-history-link"
                key={h.id}
                onClick={() => go("/orders/" + h.id)}
              >
                #{h.number} · {statusNames[h.status]}
                <small>{h.problem}</small>
              </button>
            ))}
          </aside>
        </div>
      )}
      {o.stage_forms?.[tab] && (
        <section className="w-panel">
          <h2>
            {o.stage_forms[tab].template.name} · v
            {o.stage_forms[tab].template.revision}
          </h2>
          <p className="w-muted">
            Обязательные поля проверяются при выходе с этапа, к которому
            привязана эта форма.
          </p>
          <fieldset disabled={!editable || !can("orders.edit") || a.busy}>
            <DynamicFields
              template={o.stage_forms[tab].template}
              values={stageValues[tab] || {}}
              setValues={(v) =>
                setStageValues((previous) => ({
                  ...previous,
                  [tab]: typeof v === "function" ? v(previous[tab]) : v,
                }))
              }
              can={can}
              attachments={o.attachments}
            />
          </fieldset>
          {editable && can("orders.edit") && (
            <Button
              disabled={a.busy}
              onClick={() =>
                mutate("/forms/" + tab, { values: stageValues[tab] }, "PATCH")
              }
            >
              Сохранить форму
            </Button>
          )}
        </section>
      )}
      {tab === "photos" && (
        <section className="w-panel">
          <h2>Состояние, комплектность и результаты</h2>
          {editable && can("orders.edit") && (
            <div className="w-toolbar">
              <select
                aria-label="Этап фотографии"
                value={phase}
                onChange={(e) => setPhase(e.target.value)}
              >
                {o.status === "draft" && (
                  <option value="intake">Приёмка</option>
                )}
                <option value="diagnosis">Диагностика</option>
                <option value="repair">Ремонт</option>
                <option value="quality">Финальная проверка</option>
              </select>
              <input
                aria-label="Добавить фотографию"
                type="file"
                accept="image/png,image/jpeg,image/webp,image/gif"
                disabled={a.busy}
                onChange={(e) => {
                  const file = e.target.files[0];
                  if (!file) return;
                  const data = new FormData();
                  data.append("file", file);
                  data.append("version", o.version);
                  data.append("phase", phase);
                  a.run(async () => {
                    await call("/v2/orders/" + id + "/attachments", {
                      method: "POST",
                      body: data,
                    });
                    put(await call("/v2/orders/" + id));
                  });
                  e.target.value = "";
                }}
              />
            </div>
          )}
          <div className="w-photos">
            {o.attachments.map((f) => (
              <Photo key={f.id} file={f} />
            ))}
          </div>
          {o.attachments_next && (
            <Button
              secondary
              disabled={a.busy}
              onClick={() => loadMore("attachments")}
            >
              Ещё фотографии
            </Button>
          )}
          {!o.attachments.length && (
            <p className="w-muted">Фотографии ещё не добавлены.</p>
          )}
        </section>
      )}
      {tab === "finance" && <Finance order={o} can={can} onUpdate={put} />}
      {tab === "history" && (
        <section className="w-panel">
          <h2>Журнал заказа</h2>
          {can("orders.edit") && (
            <form
              className="w-toolbar"
              onSubmit={async (e) => {
                e.preventDefault();
                if (await mutate("/notes", { text: note })) setNote("");
              }}
            >
              <input
                aria-label="Заметка"
                placeholder="Результат диагностики, звонок, договорённость…"
                required
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
              <Button disabled={a.busy}>Добавить заметку</Button>
            </form>
          )}
          <ol className="w-timeline">
            {o.events.map((e) => (
              <li key={e.id}>
                <small>
                  {time(e.created_at)} ·{" "}
                  {members.find((m) => m.id === e.actor_id)?.name ||
                    "Клиент / система"}
                </small>
                <strong>{eventName(e.kind)}</strong>
                <p>
                  {e.data.phase
                    ? o.stage_forms?.[e.data.phase]?.template.name + ": "
                    : ""}
                  {e.data.text ||
                    e.data.reason ||
                    [e.data.from, e.data.to].filter(Boolean).join(" → ") ||
                    (e.data.revision ? "Версия сметы " + e.data.revision : "")}
                </p>
                {Object.keys(e.data.value_changes || {}).length > 0 && (
                  <details>
                    <summary>Изменения полей</summary>
                    {Object.entries(e.data.value_changes).map(([key, v]) => (
                      <p key={key}>
                        {o.template.fields.find((f) => f.key === key)?.label ||
                          key}
                        : {String(v.before ?? "—")} → {String(v.after ?? "—")}
                      </p>
                    ))}
                  </details>
                )}
              </li>
            ))}
          </ol>
          {o.events_next && (
            <Button
              secondary
              disabled={a.busy}
              onClick={() => loadMore("events")}
            >
              Ранние события
            </Button>
          )}
        </section>
      )}
    </>
  );
}

export function eventName(k) {
  return (
    {
      "order.created": "Заказ создан",
      "order.accepted": "Техника принята",
      "order.edited": "Данные обновлены",
      "order.transition": "Изменён этап",
      "order.assigned": "Изменён исполнитель",
      "order.issued": "Техника выдана",
      "order.reopened": "Заказ открыт повторно",
      "order.cancelled": "Заказ отменён",
      "photo.added": "Добавлена фотография",
      "form.updated": "Обновлена форма этапа",
      "estimate.created": "Новая смета",
      "estimate.accepted": "Смета согласована",
      "estimate.declined": "Смета отклонена",
      "payment.recorded": "Оплата зарегистрирована",
      note: "Заметка",
      "warranty.created": "Гарантийное обращение",
      "warranty.linked": "Создан гарантийный возврат",
    }[k] || k
  );
}

export function IssueForm({ mutate, busy }) {
  const [receiver, setReceiver] = useState(""),
    [note, setNote] = useState(""),
    [outstanding, setOutstanding] = useState("");
  return (
    <form
      className="w-issue"
      onSubmit={(e) => {
        e.preventDefault();
        mutate("/issue", { receiver, note, outstanding_reason: outstanding });
      }}
    >
      <h3>Выдать устройство</h3>
      <Field label="Получатель">
        <input
          required
          minLength="2"
          value={receiver}
          onChange={(e) => setReceiver(e.target.value)}
        />
      </Field>
      <Field label="Примечание">
        <input value={note} onChange={(e) => setNote(e.target.value)} />
      </Field>
      <Field label="Причина выдачи при задолженности, если есть">
        <input
          value={outstanding}
          onChange={(e) => setOutstanding(e.target.value)}
        />
      </Field>
      <Button disabled={busy}>Подтвердить выдачу</Button>
    </form>
  );
}
