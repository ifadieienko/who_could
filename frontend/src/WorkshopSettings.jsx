import { useEffect, useState } from "react";
import { call, download } from "./repair-api";
import {
  Field,
  Button,
  ErrorBox,
  useAction,
  DynamicFields,
} from "./WorkshopApp";
const perms = [
  "orders.read",
  "orders.create",
  "orders.edit",
  "orders.assign",
  "orders.transition",
  "orders.issue",
  "orders.reopen",
  "contacts.read",
  "finance.read",
  "finance.write",
  "templates.manage",
  "data.export",
  "data.import",
  "billing.manage",
  "warehouse.manage",
];
const names = [
  "Просмотр заказов",
  "Приём устройств",
  "Редактирование",
  "Назначение мастеров",
  "Изменение этапов",
  "Выдача",
  "Повторное открытие",
  "Контакты клиентов",
  "Просмотр финансов",
  "Сметы и оплаты",
  "Формы и процессы",
  "Экспорт",
  "Импорт",
  "Подписка",
  "Склад",
];
const label = (p) => names[perms.indexOf(p)] || p;
const empty = () => ({
  key: "field_" + crypto.randomUUID().slice(0, 8),
  label: "",
  type: "string",
  section: "Приём",
  width: 1,
  row: null,
  required: false,
  options: [],
  condition: null,
  read_permission: null,
  write_permission: null,
});
const types = {
  string: "Короткий текст",
  text: "Длинный текст",
  number: "Число",
  date: "Дата",
  image: "Фото",
  select: "Список",
  checkbox: "Флажок",
};
export function TemplateEditor() {
  const [list, setList] = useState([]),
    [active, setActive] = useState(null),
    [name, setName] = useState(""),
    [purpose, setPurpose] = useState("intake"),
    [columns, setColumns] = useState(2),
    [fields, setFields] = useState([empty()]),
    [preview, setPreview] = useState({});
  const a = useAction();
  const choose = (t) => {
    setActive(t);
    setName(t.name);
    setColumns(t.columns);
    setPurpose(t.purpose || "intake");
    setFields(t.fields.map((f) => ({ ...f })));
  };
  const load = async (id) => {
    const all = await call("/v2/templates");
    setList(all);
    if (id) choose(all.find((t) => t.id === id));
  };
  useEffect(() => {
    a.run(() => load());
  }, []);
  const change = (i, patch) =>
    setFields(fields.map((f, n) => (n === i ? { ...f, ...patch } : f)));
  const move = (i, d) => {
    const v = [...fields];
    if (i + d < 0 || i + d >= v.length) return;
    [v[i], v[i + d]] = [v[i + d], v[i]];
    setFields(v);
  };
  return (
    <>
      <header className="w-page-head">
        <h1>Формы приёма и ремонта</h1>
        <Button
          onClick={() => {
            setActive(null);
            setName("");
            setPurpose("intake");
            setFields([empty()]);
          }}
        >
          + Форма
        </Button>
      </header>
      <ErrorBox error={a.error} />
      <div className="w-settings-layout">
        <aside className="w-panel">
          {list.map((t) => (
            <button
              className="w-history-link"
              key={t.id}
              onClick={() => choose(t)}
            >
              {t.name}
              <small>
                v{t.revision} · {t.published ? "Опубликована" : "Черновик"}
              </small>
            </button>
          ))}
        </aside>
        <section className="w-panel">
          {active?.published && (
            <div className="w-notice">
              <p>
                Опубликованная версия неизменяема. Старые заказы сохраняют свою
                копию формы.
              </p>
              <Button
                secondary
                onClick={() =>
                  a.run(async () => {
                    const r = await call(
                      "/v2/templates/" + active.id + "/version",
                      { method: "POST" },
                    );
                    await load(r.id);
                  })
                }
              >
                Создать следующую версию
              </Button>
            </div>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              a.run(async () => {
                const r = await call(
                  "/v2/templates" + (active ? "/" + active.id : ""),
                  {
                    method: active ? "PUT" : "POST",
                    body: { name, purpose, columns, fields },
                  },
                );
                await load(r.id);
              });
            }}
          >
            <fieldset disabled={active?.published || a.busy}>
              <div className="w-grid">
                <Field label="Название формы">
                  <input
                    required
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                </Field>
                <Field label="Назначение формы">
                  <select
                    value={purpose}
                    onChange={(e) => setPurpose(e.target.value)}
                  >
                    <option value="intake">Приём</option>
                    <option value="diagnosis">Диагностика</option>
                    <option value="repair">Ремонт</option>
                    <option value="quality">Проверка качества</option>
                  </select>
                </Field>
                <Field label="Количество колонок">
                  <select
                    value={columns}
                    onChange={(e) => setColumns(Number(e.target.value))}
                  >
                    {[1, 2, 3].map((n) => (
                      <option key={n}>{n}</option>
                    ))}
                  </select>
                </Field>
              </div>
              {fields.map((f, i) => (
                <article className="w-field-editor" key={i}>
                  <div className="w-field-title">
                    <strong>Поле {i + 1}</strong>
                    <div>
                      <button type="button" onClick={() => move(i, -1)}>
                        ↑
                      </button>
                      <button type="button" onClick={() => move(i, 1)}>
                        ↓
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          setFields(fields.filter((_, n) => n !== i))
                        }
                      >
                        Удалить
                      </button>
                    </div>
                  </div>
                  <div className="w-grid">
                    <Field label="Название">
                      <input
                        required
                        value={f.label}
                        onChange={(e) => change(i, { label: e.target.value })}
                      />
                    </Field>
                    <Field label="Тип">
                      <select
                        value={f.type}
                        onChange={(e) => change(i, { type: e.target.value })}
                      >
                        {Object.entries(types).map(([k, v]) => (
                          <option key={k} value={k}>
                            {v}
                          </option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Раздел">
                      <input
                        value={f.section || ""}
                        onChange={(e) => change(i, { section: e.target.value })}
                      />
                    </Field>
                    <Field label="Ширина в колонках">
                      <select
                        value={f.width || 1}
                        onChange={(e) =>
                          change(i, { width: Number(e.target.value) })
                        }
                      >
                        {[1, 2, 3].map((n) => (
                          <option key={n}>{n}</option>
                        ))}
                      </select>
                    </Field>
                    <Field label="Строка (пусто — автоматически)">
                      <input
                        type="number"
                        min="1"
                        max="100"
                        value={f.row || ""}
                        onChange={(e) =>
                          change(i, { row: Number(e.target.value) || null })
                        }
                      />
                    </Field>
                    <label className="w-check">
                      <input
                        type="checkbox"
                        checked={f.required}
                        onChange={(e) =>
                          change(i, { required: e.target.checked })
                        }
                      />
                      Обязательно при приёме
                    </label>
                  </div>
                  {f.type === "select" && (
                    <Field label="Варианты — каждый с новой строки">
                      <textarea
                        value={f.options.join("\n")}
                        onChange={(e) =>
                          change(i, { options: e.target.value.split("\n") })
                        }
                      />
                    </Field>
                  )}
                  <details>
                    <summary>Условия и права</summary>
                    <Field label="Ключ для правил процесса">
                      <input
                        required
                        pattern="[a-zA-Z][a-zA-Z0-9_]*"
                        value={f.key}
                        onChange={(e) => change(i, { key: e.target.value })}
                      />
                    </Field>
                    <div className="w-grid">
                      <Field label="Показывать, если поле">
                        <select
                          value={f.condition?.field || ""}
                          onChange={(e) =>
                            change(i, {
                              condition: e.target.value
                                ? {
                                    field: e.target.value,
                                    equals:
                                      fields.find(
                                        (f) => f.key === e.target.value,
                                      )?.type === "checkbox"
                                        ? true
                                        : "",
                                  }
                                : null,
                            })
                          }
                        >
                          <option value="">Всегда</option>
                          {fields
                            .filter((x) => x.key !== f.key && !x.condition)
                            .map((x) => (
                              <option key={x.key} value={x.key}>
                                {x.label || x.key}
                              </option>
                            ))}
                        </select>
                      </Field>
                      {f.condition && (
                        <Field label="Равно (для флажка: true/false)">
                          {fields.find((x) => x.key === f.condition.field)
                            ?.type === "checkbox" ? (
                            <select
                              value={String(f.condition.equals)}
                              onChange={(e) =>
                                change(i, {
                                  condition: {
                                    ...f.condition,
                                    equals: e.target.value === "true",
                                  },
                                })
                              }
                            >
                              <option value="true">Отмечено</option>
                              <option value="false">Не отмечено</option>
                            </select>
                          ) : (
                            <input
                              value={String(f.condition.equals)}
                              onChange={(e) => {
                                const p = fields.find(
                                  (x) => x.key === f.condition.field,
                                );
                                change(i, {
                                  condition: {
                                    ...f.condition,
                                    equals:
                                      p?.type === "number"
                                        ? Number(e.target.value)
                                        : e.target.value,
                                  },
                                });
                              }}
                            />
                          )}
                        </Field>
                      )}
                      {["read_permission", "write_permission"].map((k) => (
                        <Field
                          key={k}
                          label={
                            k === "read_permission"
                              ? "Право для просмотра"
                              : "Право для изменения"
                          }
                        >
                          <select
                            value={f[k] || ""}
                            onChange={(e) =>
                              change(i, { [k]: e.target.value || null })
                            }
                          >
                            <option value="">Обычный доступ к заказу</option>
                            {perms.map((p) => (
                              <option key={p} value={p}>
                                {label(p)}
                              </option>
                            ))}
                          </select>
                        </Field>
                      ))}
                    </div>
                  </details>
                </article>
              ))}
              <div className="w-actions">
                <Button
                  secondary
                  type="button"
                  onClick={() => setFields([...fields, empty()])}
                >
                  + Поле
                </Button>
                <Button>Сохранить черновик</Button>
              </div>
            </fieldset>
          </form>
          {active && (
            <div className="w-actions">
              {!active.published && (
                <Button
                  disabled={a.busy}
                  onClick={() =>
                    a.run(async () => {
                      await call("/v2/templates/" + active.id + "/publish", {
                        method: "POST",
                      });
                      await load(active.id);
                    })
                  }
                >
                  Опубликовать сохранённую версию
                </Button>
              )}
              <Button
                secondary
                onClick={() =>
                  a.run(async () => {
                    if (!confirm("Архивировать шаблон? Заказы сохранятся."))
                      return;
                    await call("/v2/templates/" + active.id + "/archive", {
                      method: "POST",
                    });
                    setActive(null);
                    setName("");
                    setPurpose("intake");
                    setFields([empty()]);
                    await load();
                  })
                }
              >
                Архивировать
              </Button>
            </div>
          )}
          <hr />
          <h2>Предпросмотр формы</h2>
          <DynamicFields
            template={{ fields, layout: { columns } }}
            values={preview}
            setValues={setPreview}
            can={() => true}
            attachments={[]}
          />
          <p className="w-muted">
            На телефоне поля располагаются в одну колонку. Данные предпросмотра
            не сохраняются.
          </p>
        </section>
      </div>
    </>
  );
}
export function WorkflowEditor() {
  const [list, setList] = useState([]),
    [active, setActive] = useState(null),
    [name, setName] = useState(""),
    [stages, setStages] = useState([]);
  const a = useAction();
  const choose = (w) => {
    setActive(w);
    setName(w.name);
    setStages(
      w.stages.map((s) => ({
        checks: [],
        required_fields: [],
        permission: "orders.transition",
        requires_quote: false,
        ...s,
      })),
    );
  };
  useEffect(() => {
    a.run(async () => {
      const all = await call("/v2/workflows");
      setList(all);
      if (all[0]) choose(all[0]);
    });
  }, []);
  const change = (i, p) =>
    setStages(stages.map((s, n) => (n === i ? { ...s, ...p } : s)));
  return (
    <>
      <header className="w-page-head">
        <h1>Этапы и правила ремонта</h1>
        <Button
          onClick={() => {
            setActive(null);
            setName("Новый процесс");
            setStages([
              {
                key: "received",
                name: "Принято",
                category: "active",
                next: ["ready"],
                checks: [],
                required_fields: [],
                sla_hours: 48,
              },
              {
                key: "ready",
                name: "Готово",
                category: "ready",
                next: ["received"],
                checks: ["Финальный тест"],
                required_fields: [],
                sla_hours: 168,
              },
            ]);
          }}
        >
          + Процесс
        </Button>
      </header>
      <ErrorBox error={a.error} />
      <div className="w-tabs">
        {list.map((w) => (
          <button
            key={w.id}
            onClick={() => choose(w)}
            className={w.id === active?.id ? "active" : ""}
          >
            {w.name} · v{w.revision}
          </button>
        ))}
      </div>
      <form
        className="w-panel"
        onSubmit={(e) => {
          e.preventDefault();
          a.run(async () => {
            const r = await call(
              "/v2/workflows" + (active ? "/" + active.id + "/version" : ""),
              {
                method: "POST",
                body: {
                  name,
                  stages: stages.map((s) => ({
                    ...s,
                    checks: s.checks.map((x) => x.trim()).filter(Boolean),
                    required_fields: s.required_fields
                      .map((x) => x.trim())
                      .filter(Boolean),
                  })),
                },
              },
            );
            const all = await call("/v2/workflows");
            setList(all);
            choose(all.find((w) => w.id === r.id));
          });
        }}
      >
        <Field label="Название процесса">
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        <p className="w-muted">
          Новая версия действует для будущих заказов. Открытые ремонты сохраняют
          прежние правила. Первый этап используется при приёме.
        </p>
        {stages.map((s, i) => (
          <article className="w-field-editor" key={s.key}>
            <div className="w-field-title">
              <strong>
                {i + 1}. {s.name}
              </strong>
              <button
                type="button"
                disabled={stages.length <= 2}
                onClick={() =>
                  setStages(
                    stages
                      .filter((_, n) => n !== i)
                      .map((x) => ({
                        ...x,
                        next: x.next.filter((k) => k !== s.key),
                      })),
                  )
                }
              >
                Удалить
              </button>
            </div>
            <div className="w-grid three">
              <Field label="Название">
                <input
                  required
                  value={s.name}
                  onChange={(e) => change(i, { name: e.target.value })}
                />
              </Field>
              <Field label="Состояние">
                <select
                  value={s.category}
                  onChange={(e) => change(i, { category: e.target.value })}
                >
                  <option value="active">Работа</option>
                  <option value="waiting">Ожидание</option>
                  <option value="ready">Готово к выдаче</option>
                </select>
              </Field>
              <Field label="Задержка, часов">
                <input
                  type="number"
                  min="1"
                  max="8760"
                  value={s.sla_hours}
                  onChange={(e) =>
                    change(i, { sla_hours: Number(e.target.value) })
                  }
                />
              </Field>
            </div>
            <p>Разрешённые следующие этапы:</p>
            <div className="w-check-grid">
              {stages
                .filter((t) => t.key !== s.key)
                .map((t) => (
                  <label key={t.key} className="w-check">
                    <input
                      type="checkbox"
                      checked={s.next.includes(t.key)}
                      onChange={(e) =>
                        change(i, {
                          next: e.target.checked
                            ? [...s.next, t.key]
                            : s.next.filter((k) => k !== t.key),
                        })
                      }
                    />
                    {t.name}
                  </label>
                ))}
            </div>
            <div className="w-grid">
              <Field label="Форма для завершения этапа">
                <select
                  value={s.form_phase || ""}
                  onChange={(e) =>
                    change(i, { form_phase: e.target.value || null })
                  }
                >
                  <option value="">Без отдельной формы</option>
                  <option value="diagnosis">Диагностика</option>
                  <option value="repair">Ремонт</option>
                  <option value="quality">Проверка качества</option>
                </select>
              </Field>
              <Field label="Обязательные ключи полей — через запятую">
                <input
                  value={s.required_fields.join(",")}
                  onChange={(e) =>
                    change(i, { required_fields: e.target.value.split(",") })
                  }
                />
              </Field>
              <Field label="Право для перехода">
                <select
                  value={s.permission || "orders.transition"}
                  onChange={(e) => change(i, { permission: e.target.value })}
                >
                  {perms.map((p) => (
                    <option key={p} value={p}>
                      {label(p)}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <Field label="Обязательные проверки — каждая с новой строки">
              <textarea
                value={s.checks.join("\n")}
                onChange={(e) =>
                  change(i, { checks: e.target.value.split("\n") })
                }
              />
            </Field>
            <label className="w-check">
              <input
                type="checkbox"
                checked={Boolean(s.requires_quote)}
                onChange={(e) =>
                  change(i, { requires_quote: e.target.checked })
                }
              />
              Требуется согласованная актуальная смета
            </label>
          </article>
        ))}
        <div className="w-actions">
          <Button
            secondary
            type="button"
            onClick={() =>
              setStages([
                ...stages,
                {
                  key: "stage_" + crypto.randomUUID().slice(0, 8),
                  name: "Новый этап",
                  category: "active",
                  next: [],
                  checks: [],
                  required_fields: [],
                  sla_hours: 48,
                },
              ])
            }
          >
            + Этап
          </Button>
          <Button disabled={a.busy}>Сохранить новую версию</Button>
        </div>
      </form>
    </>
  );
}
export function Team({ user }) {
  const [members, setMembers] = useState([]),
    [roles, setRoles] = useState([]),
    [form, setForm] = useState({
      name: "",
      email: "",
      password: "",
      role_id: "",
    }),
    [role, setRole] = useState({
      name: "",
      scope: "all",
      permissions: ["orders.read"],
    });
  const a = useAction();
  const load = async () => {
    const [m, r] = await Promise.all([call("/v2/members"), call("/v2/roles")]);
    setMembers(m);
    setRoles(r.roles);
  };
  useEffect(() => {
    a.run(load);
  }, []);
  const change = async (m, p) => {
    await call("/v2/members/" + m.id, {
      method: "PATCH",
      body: { role_id: m.role_id, active: m.active, ...p },
    });
    await load();
  };
  return (
    <>
      <h1>Команда мастерской</h1>
      <ErrorBox error={a.error} />
      <section className="w-panel">
        <table className="w-table">
          <thead>
            <tr>
              <th>Сотрудник</th>
              <th>Роль</th>
              <th>Доступ</th>
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.id}>
                <td>
                  {m.name}
                  <small>{m.email}</small>
                </td>
                <td>
                  <select
                    disabled={m.owner || a.busy}
                    value={m.role_id}
                    onChange={(e) =>
                      a.run(() =>
                        change(m, { role_id: Number(e.target.value) }),
                      )
                    }
                  >
                    {roles
                      .filter((r) => !r.owner || m.owner)
                      .map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.name}
                        </option>
                      ))}
                  </select>
                </td>
                <td>
                  <Button
                    secondary
                    disabled={m.owner || m.id === user.id || a.busy}
                    onClick={() =>
                      a.run(() => change(m, { active: !m.active }))
                    }
                  >
                    {m.active ? "Отключить" : "Включить"}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="w-muted">
          Отключение доступа сохраняет историю сотрудника и все заказы.
        </p>
      </section>
      <div className="w-grid">
        <form
          className="w-panel"
          onSubmit={(e) => {
            e.preventDefault();
            a.run(async () => {
              await call("/v2/members", {
                method: "POST",
                body: { ...form, role_id: Number(form.role_id) },
              });
              setForm({ name: "", email: "", password: "", role_id: "" });
              await load();
            });
          }}
        >
          <h2>Добавить сотрудника</h2>
          {[
            ["name", "Имя", "text"],
            ["email", "Email", "email"],
            ["password", "Начальный пароль (от 12 символов)", "password"],
          ].map(([k, l, t]) => (
            <Field key={k} label={l}>
              <input
                required
                type={t}
                minLength={k === "password" ? 12 : 2}
                value={form[k]}
                onChange={(e) => setForm({ ...form, [k]: e.target.value })}
              />
            </Field>
          ))}
          <Field label="Роль">
            <select
              required
              value={form.role_id}
              onChange={(e) => setForm({ ...form, role_id: e.target.value })}
            >
              <option value="">Выберите</option>
              {roles
                .filter((r) => !r.owner)
                .map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
            </select>
          </Field>
          <Button disabled={a.busy}>Создать аккаунт</Button>
        </form>
        <form
          className="w-panel"
          onSubmit={(e) => {
            e.preventDefault();
            a.run(async () => {
              const { id, ...body } = role;
              await call("/v2/roles" + (id ? "/" + id : ""), {
                method: id ? "PUT" : "POST",
                body,
              });
              setRole({ name: "", scope: "all", permissions: ["orders.read"] });
              await load();
            });
          }}
        >
          <h2>Права роли</h2>
          <select
            aria-label="Редактировать роль"
            value={role.id || ""}
            onChange={(e) => {
              const r = roles.find((r) => r.id === Number(e.target.value));
              setRole(
                r
                  ? {
                      id: r.id,
                      name: r.name,
                      scope: r.scope,
                      permissions: r.permissions,
                    }
                  : { name: "", scope: "all", permissions: ["orders.read"] },
              );
            }}
          >
            <option value="">Новая роль</option>
            {roles
              .filter((r) => !r.owner)
              .map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
          </select>
          <Field label="Название">
            <input
              required
              value={role.name}
              onChange={(e) => setRole({ ...role, name: e.target.value })}
            />
          </Field>
          <Field label="Область заказов">
            <select
              value={role.scope}
              onChange={(e) => setRole({ ...role, scope: e.target.value })}
            >
              <option value="all">Вся мастерская</option>
              <option value="own">Свои и свободные</option>
            </select>
          </Field>
          <div className="w-check-grid">
            {perms.map((p) => (
              <label key={p} className="w-check">
                <input
                  type="checkbox"
                  checked={role.permissions.includes(p)}
                  onChange={(e) =>
                    setRole({
                      ...role,
                      permissions: e.target.checked
                        ? [...role.permissions, p]
                        : role.permissions.filter((x) => x !== p),
                    })
                  }
                />
                {label(p)}
              </label>
            ))}
          </div>
          <Button disabled={a.busy}>Сохранить роль</Button>
        </form>
      </div>
    </>
  );
}
export function Transfer() {
  const [templates, setTemplates] = useState([]),
    [flows, setFlows] = useState([]),
    [template, setTemplate] = useState(""),
    [workflow, setWorkflow] = useState(""),
    [kind, setKind] = useState("orders"),
    [file, setFile] = useState(null),
    [result, setResult] = useState(null);
  const a = useAction();
  useEffect(() => {
    a.run(async () => {
      const [t, w] = await Promise.all([
        call("/v2/templates"),
        call("/v2/workflows"),
      ]);
      setTemplates(t.filter((x) => x.published && x.purpose === "intake"));
      setFlows(w);
      setTemplate(t.find((x) => x.published && x.purpose === "intake")?.id);
      setWorkflow(w[0]?.id);
    });
  }, []);
  const send = (dry) =>
    a.run(async () => {
      const body = new FormData();
      body.append("file", file);
      body.append("template_id", template);
      body.append("workflow_id", workflow);
      body.append("kind", kind);
      body.append("dry_run", String(dry));
      setResult(await call("/v2/import/csv", { method: "POST", body }));
    });
  const sample = () => {
    const blob = new Blob(
      [
        "external_id,customer_external_id,name,email,phone,model,serial,problem,condition,accessories,location\norder-1,client-1,Jan Kowalski,jan@example.com,123456789,ThinkPad X1,SN123,Не включается,Царапины,Зарядка,B-12\n",
      ],
      { type: "text/csv;charset=utf-8" },
    );
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "orders-import-example.csv";
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  };
  return (
    <>
      <h1>Импорт и экспорт</h1>
      <ErrorBox error={a.error} />
      <div className="w-grid">
        <section className="w-panel">
          <h2>Импорт CSV</h2>
          <p>
            UTF-8, разделитель — запятая, до 1000 строк. Повторные external_id
            пропускаются. Заказы создаются в черновиках.
          </p>
          <Button secondary onClick={sample}>
            Скачать пример CSV
          </Button>
          <Field label="Тип данных">
            <select
              value={kind}
              onChange={(e) => {
                setKind(e.target.value);
                setResult(null);
              }}
            >
              <option value="orders">Заказы</option>
              <option value="customers">Клиенты</option>
            </select>
          </Field>
          <Field label="Форма">
            <select
              value={template}
              onChange={(e) => {
                setTemplate(e.target.value);
                setResult(null);
              }}
            >
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Процесс">
            <select
              value={workflow}
              onChange={(e) => {
                setWorkflow(e.target.value);
                setResult(null);
              }}
            >
              {flows.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="CSV файл">
            <input
              type="file"
              accept=".csv"
              onChange={(e) => {
                setFile(e.target.files[0]);
                setResult(null);
              }}
            />
          </Field>
          <div className="w-actions">
            <Button
              secondary
              disabled={!file || a.busy}
              onClick={() => send(true)}
            >
              Проверить файл
            </Button>
            <Button
              disabled={a.busy || !result?.valid || !result?.dry_run}
              onClick={() => send(false)}
            >
              Импортировать
            </Button>
          </div>
          {result && (
            <div className="w-notice">
              <p>
                {result.dry_run ? "Проверка" : "Импорт завершён"}:{" "}
                {result.created} новых, {result.skipped} пропущено.
              </p>
              {result.errors.map((e, i) => (
                <p key={i}>
                  Строка {e.line}: {e.message}
                </p>
              ))}
            </div>
          )}
        </section>
        <section className="w-panel">
          <h2>Полный экспорт</h2>
          <p>
            ZIP: клиенты, устройства, заказы, шаблоны, процессы, сметы, оплаты,
            история, склад и фотографии. Пароли и секретные ссылки не
            включаются.
          </p>
          <Button
            disabled={a.busy}
            onClick={() =>
              a.run(() => download("/v2/export", "workshop-export.zip"))
            }
          >
            Скачать архив мастерской
          </Button>
          <p className="w-muted">
            Доступен после окончания подписки. CSV-импорт и архив экспорта имеют
            разные форматы.
          </p>
        </section>
      </div>
    </>
  );
}
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
