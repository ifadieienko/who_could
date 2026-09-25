import {
  Button,
  ErrorBox,
  Field,
  useAction,
} from "../../components/workshop/ui.jsx";
import { call } from "../../repair-api.js";
import { label, perms } from "../forms/editor-options.js";
import { useEffect, useState } from "react";

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
