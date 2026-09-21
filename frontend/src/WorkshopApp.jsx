import { useEffect, useState } from "react";
import {
  call,
  getWorkshop,
  setWorkshop,
  download,
  printDocument,
} from "./repair-api";
import { Warehouse } from "./Warehouse";
import {
  TemplateEditor,
  WorkflowEditor,
  Team,
  Transfer,
  Billing,
} from "./WorkshopSettings";
import "./workshop.css";

const money = (n) => `${((n || 0) / 100).toFixed(2)} PLN`;
const dateValue = (v) => new Date(/(Z|[+-]\d\d:\d\d)$/.test(v) ? v : v + "Z");
const time = (v) => (v ? dateValue(v).toLocaleString() : "—");
const localInput = (v) => {
  if (!v) return "";
  const d = dateValue(v);
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
};
const statusNames = {
  draft: "Черновик",
  active: "В работе",
  waiting: "Ожидание",
  ready: "К выдаче",
  issued: "Выдан",
  cancelled: "Отменён",
  pending: "Ожидает решения",
  accepted: "Принята",
  declined: "Отклонена",
  superseded: "Заменена",
};
export function Field({ label, children }) {
  return (
    <label className="w-field">
      <span>{label}</span>
      {children}
    </label>
  );
}
export function Button({ children, secondary, ...props }) {
  return (
    <button
      className={secondary ? "w-button secondary" : "w-button"}
      {...props}
    >
      {children}
    </button>
  );
}
export function ErrorBox({ error }) {
  return error ? (
    <div className="w-error" role="alert">
      {error}
    </div>
  ) : null;
}
export function useAction() {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const run = async (fn) => {
    setBusy(true);
    setError("");
    try {
      return await fn();
    } catch (e) {
      setError(e.message);
      return undefined;
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, run, setError };
}
function go(path) {
  window.history.pushState({}, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export default function WorkshopApp() {
  const [user, setUser] = useState(null),
    [shops, setShops] = useState([]),
    [selected, setSelected] = useState(getWorkshop());
  const [path, setPath] = useState(window.location.pathname),
    [loading, setLoading] = useState(true);
  const action = useAction();
  const load = async () => {
    try {
      const u = await call("/me");
      const ws = await call("/v2/workshops");
      setUser(u);
      setShops(ws);
      const requested =
        Number(new URLSearchParams(window.location.search).get("workshop")) ||
        getWorkshop();
      const id = ws.some((x) => x.id === requested) ? requested : ws[0]?.id;
      if (id) {
        setWorkshop(id);
        setSelected(id);
      }
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    load();
    const change = () => setPath(window.location.pathname),
      cleared = () => setUser(null);
    window.addEventListener("popstate", change);
    window.addEventListener("who-could:session-cleared", cleared);
    return () => {
      window.removeEventListener("popstate", change);
      window.removeEventListener("who-could:session-cleared", cleared);
    };
  }, []);
  if (path.startsWith("/quote/"))
    return <QuotePortal token={path.split("/")[2]} />;
  if (path.startsWith("/reset/"))
    return <ResetPassword token={path.split("/")[2]} />;
  if (loading) return <div className="w-loading">Загрузка мастерской…</div>;
  if (!user) return <Auth onLogin={load} />;
  const shop = shops.find((x) => x.id === selected),
    can = (p) => shop?.permissions.includes(p);
  const nav = [
    ["/orders", "Заказы", "orders.read"],
    ["/templates", "Формы", "templates.manage"],
    ["/workflows", "Процессы", "templates.manage"],
    ["/warehouse", "Склад", "warehouse.manage"],
    ["/team", "Команда", "members.manage"],
    ["/data", "Перенос данных", "data.export"],
    ["/billing", "Подписка", "billing.manage"],
  ].filter((x) => can(x[2]));
  const logout = () =>
    action.run(async () => {
      await call("/auth/logout", { method: "POST" });
      setUser(null);
    });
  return (
    <div className="w-app">
      <aside className="w-sidebar">
        <div className="w-brand">
          W
          <span>
            Who Could<small>Рабочее место мастерской</small>
          </span>
        </div>
        <select
          aria-label="Мастерская"
          value={selected || ""}
          onChange={(e) => {
            setWorkshop(e.target.value);
            setSelected(Number(e.target.value));
            go("/orders");
          }}
        >
          {shops.map((w) => (
            <option key={w.id} value={w.id}>
              {w.name}
            </option>
          ))}
        </select>
        <nav>
          {nav.map(([url, name]) => (
            <button
              key={url}
              className={path.startsWith(url) ? "active" : ""}
              onClick={() => go(url)}
            >
              {name}
            </button>
          ))}
        </nav>
        <div className="w-account">
          <strong>{user.name}</strong>
          <small>{user.email}</small>
          <Button secondary onClick={logout}>
            Выйти
          </Button>
        </div>
      </aside>
      <main className="w-main" key={selected}>
        <ErrorBox error={action.error} />
        {!shop ? (
          <p>Доступ к мастерской отключён. Обратитесь к владельцу.</p>
        ) : path === "/templates" ? (
          <TemplateEditor />
        ) : path === "/workflows" ? (
          <WorkflowEditor />
        ) : path === "/team" ? (
          <Team user={user} />
        ) : path === "/data" ? (
          <Transfer />
        ) : path === "/billing" ? (
          <Billing />
        ) : path === "/warehouse" ? (
          <Warehouse user={user} />
        ) : path === "/orders/new" ? (
          <NewOrder can={can} />
        ) : /^\/orders\/[^/]+$/.test(path) ? (
          <OrderDetail id={path.split("/")[2]} can={can} user={user} />
        ) : (
          <Orders can={can} />
        )}
      </main>
    </div>
  );
}

function Auth({ onLogin }) {
  const [register, setRegister] = useState(false),
    [form, setForm] = useState({
      name: "",
      email: "",
      password: "",
      workshop: "",
    }),
    [notice, setNotice] = useState("");
  const a = useAction();
  const submit = (e) => {
    e.preventDefault();
    a.run(async () => {
      await call(register ? "/auth/register" : "/auth/login", {
        method: "POST",
        body: register ? form : { email: form.email, password: form.password },
      });
      await onLogin();
    });
  };
  return (
    <div className="w-auth">
      <div className="w-auth-intro">
        <p className="w-eyebrow">WHO COULD / WORKSHOP</p>
        <h1>
          Каждый ремонт.
          <br />
          От приёма до выдачи.
        </h1>
        <p>
          Заказы, фотографии, сметы и проверки — в одной истории устройства.
        </p>
      </div>
      <form className="w-panel" onSubmit={submit}>
        <h2>{register ? "Создать мастерскую" : "Войти в мастерскую"}</h2>
        <ErrorBox error={a.error} />
        {register && (
          <>
            <Field label="Ваше имя">
              <input
                required
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </Field>
            <Field label="Название мастерской">
              <input
                required
                value={form.workshop}
                onChange={(e) => setForm({ ...form, workshop: e.target.value })}
              />
            </Field>
          </>
        )}
        <Field label="Email">
          <input
            type="email"
            required
            autoComplete="username"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
        </Field>
        <Field label="Пароль">
          <input
            type="password"
            required
            minLength={register ? 12 : 1}
            autoComplete={register ? "new-password" : "current-password"}
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
        </Field>
        <Button disabled={a.busy}>
          {register ? "Начать работу" : "Войти"}
        </Button>
        <Button secondary type="button" onClick={() => setRegister(!register)}>
          {register ? "Уже есть аккаунт" : "Новая мастерская"}
        </Button>
        {!register && (
          <Button
            secondary
            type="button"
            onClick={() =>
              a.run(async () => {
                const r = await call("/auth/reset-request", {
                  method: "POST",
                  body: { email: form.email },
                });
                setNotice(r.message);
              })
            }
          >
            Восстановить пароль
          </Button>
        )}
        {notice && <p>{notice}</p>}
      </form>
    </div>
  );
}
function ResetPassword({ token }) {
  const [password, setPassword] = useState(""),
    [done, setDone] = useState(false);
  const a = useAction();
  return (
    <div className="w-public">
      <form
        className="w-panel"
        onSubmit={(e) => {
          e.preventDefault();
          a.run(async () => {
            await call("/auth/reset-password", {
              method: "POST",
              body: { token, password },
            });
            setDone(true);
          });
        }}
      >
        <h1>Новый пароль</h1>
        <ErrorBox error={a.error} />
        {done ? (
          <a href="/">Войти с новым паролем</a>
        ) : (
          <>
            <input
              aria-label="Новый пароль"
              type="password"
              minLength="12"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <Button disabled={a.busy}>Сохранить</Button>
          </>
        )}
      </form>
    </div>
  );
}
function Orders({ can }) {
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
function NewOrder() {
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

function Photo({ file }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    let alive = true,
      object;
    call("/v2/files/" + file.id + "?thumb=true", { raw: true })
      .then((blob) => {
        object = URL.createObjectURL(blob);
        if (alive) setUrl(object);
        else URL.revokeObjectURL(object);
      })
      .catch(() => {});
    return () => {
      alive = false;
      if (object) URL.revokeObjectURL(object);
    };
  }, [file.id]);
  return (
    <figure>
      <button onClick={() => download("/v2/files/" + file.id, file.filename)}>
        {url ? <img src={url} alt={file.filename} /> : <span>Фото</span>}
      </button>
      <figcaption>
        {file.phase} · {time(file.created_at)}
      </figcaption>
    </figure>
  );
}
export function DynamicFields({
  template,
  values,
  setValues,
  can,
  attachments,
}) {
  return (
    <div
      className="w-dynamic"
      style={{ "--columns": template.layout?.columns || 2 }}
    >
      {template.fields
        .filter(
          (f) =>
            !f.condition || values[f.condition.field] === f.condition.equals,
        )
        .map((f) => {
          const value = values[f.key] ?? "",
            disabled = f.write_permission && !can(f.write_permission);
          const set = (v) => setValues({ ...values, [f.key]: v });
          return (
            <div
              key={f.key}
              style={{
                gridColumn: `span ${Math.min(f.width || 1, template.layout?.columns || 2)}`,
                gridRowStart: f.row || "auto",
              }}
            >
              <Field
                label={`${f.label}${f.required ? " *" : ""}${f.section ? " · " + f.section : ""}`}
              >
                {f.type === "checkbox" ? (
                  <input
                    type="checkbox"
                    disabled={disabled}
                    checked={Boolean(value)}
                    onChange={(e) => set(e.target.checked)}
                  />
                ) : f.type === "select" ? (
                  <select
                    disabled={disabled}
                    value={value}
                    onChange={(e) => set(e.target.value)}
                  >
                    <option value="">Выберите</option>
                    {f.options.map((x) => (
                      <option key={x}>{x}</option>
                    ))}
                  </select>
                ) : f.type === "image" ? (
                  typeof value === "string" && value.startsWith("data:") ? (
                    <img className="w-legacy-photo" src={value} alt={f.label} />
                  ) : (
                    <select
                      disabled={disabled}
                      value={value}
                      onChange={(e) =>
                        set(e.target.value ? Number(e.target.value) : null)
                      }
                    >
                      <option value="">Выберите загруженное фото</option>
                      {value && !attachments.some((x) => x.id === value) && (
                        <option value={value}>
                          Фото #{value} · ранее загружено
                        </option>
                      )}
                      {attachments.map((x) => (
                        <option key={x.id} value={x.id}>
                          {x.filename} · #{x.id}
                        </option>
                      ))}
                    </select>
                  )
                ) : f.type === "text" ? (
                  <textarea
                    disabled={disabled}
                    value={value}
                    onChange={(e) => set(e.target.value)}
                  />
                ) : (
                  <input
                    disabled={disabled}
                    type={
                      f.type === "number"
                        ? "number"
                        : f.type === "date"
                          ? "date"
                          : "text"
                    }
                    value={value}
                    onChange={(e) =>
                      set(
                        f.type === "number" && e.target.value !== ""
                          ? Number(e.target.value)
                          : e.target.value,
                      )
                    }
                  />
                )}
              </Field>
            </div>
          );
        })}
    </div>
  );
}

function OrderDetail({ id, can, user }) {
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
        due_at: meta.due_at ? new Date(meta.due_at).toISOString() : null,
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
                          due_at: meta.due_at
                            ? new Date(meta.due_at).toISOString()
                            : null,
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
function eventName(k) {
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
function IssueForm({ mutate, busy }) {
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
function Finance({ order: o, can, onUpdate }) {
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
function QuotePortal({ token }) {
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
