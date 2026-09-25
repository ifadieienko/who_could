import { Field } from "../../components/workshop/ui.jsx";
import { label } from "./editor-options.js";

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
