import { Field } from "../../components/workshop/ui.jsx";
import { SelectControl } from "../../components/workshop/SelectControl.jsx";
import { t } from "../../app/i18n.js";

export const newColumn = () => ({
  key: "column_" + crypto.randomUUID().slice(0, 8),
  label: "",
  type: "number",
  required: false,
  options: [],
  unit: "",
  min: null,
  max: null,
  precision: null,
});

export function TableColumnsEditor({ field, onChange }) {
  const columns = field.columns || [];
  const change = (index, patch) =>
    onChange({
      columns: columns.map((c, i) => (i === index ? { ...c, ...patch } : c)),
    });
  return (
    <section className="w-table-editor" aria-label={t("tableColumns")}>
      <h3>{t("tableColumns")}</h3>
      <div className="w-grid">
        {["min_rows", "max_rows"].map((key) => (
          <Field
            key={key}
            label={t(key === "min_rows" ? "tableMinRows" : "tableMaxRows")}
          >
            <input
              type="number"
              required
              min={key === "min_rows" ? 0 : 1}
              max={100}
              value={field[key] ?? (key === "min_rows" ? 0 : 100)}
              onChange={(e) =>
                onChange({
                  [key]: e.target.value === "" ? "" : Number(e.target.value),
                })
              }
            />
          </Field>
        ))}
      </div>
      {columns.map((c, index) => (
        <article className="w-table-column" key={index}>
          <div className="w-field-title">
            <strong>
              {t("tableColumn")} {index + 1}
            </strong>
            <div>
              <button
                type="button"
                aria-label={`${t("tableMoveUp")} ${index + 1}`}
                disabled={index === 0}
                onClick={() => {
                  const next = [...columns];
                  [next[index - 1], next[index]] = [
                    next[index],
                    next[index - 1],
                  ];
                  onChange({ columns: next });
                }}
              >
                ↑
              </button>
              <button
                type="button"
                aria-label={`${t("tableRemoveColumn")} ${index + 1}`}
                onClick={() =>
                  onChange({ columns: columns.filter((_, i) => i !== index) })
                }
              >
                {t("tableRemove")}
              </button>
            </div>
          </div>
          <div className="w-grid">
            <Field label={t("tableColumnLabel")}>
              <input
                required
                maxLength={120}
                value={c.label}
                onChange={(e) => change(index, { label: e.target.value })}
              />
            </Field>
            <Field label={t("tableColumnType")}>
              <SelectControl
                value={c.type}
                onChange={(e) =>
                  change(index, {
                    type: e.target.value,
                    min: null,
                    max: null,
                    precision: null,
                  })
                }
              >
                {["string", "text", "number", "date", "select", "checkbox"].map(
                  (type) => (
                    <option key={type} value={type}>
                      {t("tableType_" + type)}
                    </option>
                  ),
                )}
              </SelectControl>
            </Field>
            <Field label={t("tableUnit")}>
              <input
                maxLength={24}
                value={c.unit || ""}
                onChange={(e) => change(index, { unit: e.target.value })}
              />
            </Field>
            <label className="w-check">
              <input
                type="checkbox"
                checked={c.required}
                onChange={(e) => change(index, { required: e.target.checked })}
              />
              {t("tableRequired")}
            </label>
          </div>
          {c.type === "select" && (
            <Field label={t("tableOptions")}>
              <textarea
                required
                value={(c.options || []).join("\n")}
                onChange={(e) =>
                  change(index, { options: e.target.value.split("\n") })
                }
              />
            </Field>
          )}
          {c.type === "number" && (
            <div className="w-grid">
              {["min", "max", "precision"].map((key) => (
                <Field key={key} label={t("table_" + key)}>
                  <input
                    type="number"
                    step={key === "precision" ? 1 : "any"}
                    min={key === "precision" ? 0 : undefined}
                    max={key === "precision" ? 10 : undefined}
                    value={c[key] ?? ""}
                    onChange={(e) =>
                      change(index, {
                        [key]:
                          e.target.value === "" ? null : Number(e.target.value),
                      })
                    }
                  />
                </Field>
              ))}
            </div>
          )}
          <details>
            <summary>{t("tableColumnKey")}</summary>
            <input
              aria-label={t("tableColumnKey")}
              required
              pattern="[a-zA-Z][a-zA-Z0-9_]{0,63}"
              value={c.key}
              onChange={(e) => change(index, { key: e.target.value })}
            />
          </details>
        </article>
      ))}
      <button
        type="button"
        className="w-button secondary"
        disabled={columns.length >= 12}
        onClick={() => onChange({ columns: [...columns, newColumn()] })}
      >
        + {t("tableAddColumn")}
      </button>
      <p className="w-muted">{t("tableHelp")}</p>
    </section>
  );
}
