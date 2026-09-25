import {
  Button,
  ErrorBox,
  Field,
  useAction,
} from "../../components/workshop/ui.jsx";
import { DynamicFields } from "./DynamicFields.jsx";
import { call } from "../../repair-api.js";
import { empty, label, perms, types } from "./editor-options.js";
import { useEffect, useState } from "react";

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
