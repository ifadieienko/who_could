import { SelectControl } from "../../components/workshop/SelectControl.jsx";
import { t } from "../../app/i18n.js";

export function TableField({ field, value, onChange, disabled }) {
  const rows = Array.isArray(value) ? value : [];
  const columns = field.columns || [];
  const setCell = (index, key, next) =>
    onChange(
      rows.map((row, i) => (i === index ? { ...row, [key]: next } : row)),
    );
  return (
    <fieldset className="w-form-table" disabled={disabled}>
      <legend>
        {field.label}
        {field.required ? " *" : ""}
      </legend>
      <div
        className="w-form-table-scroll"
        tabIndex={0}
        role="region"
        aria-label={field.label}
      >
        <table>
          <thead>
            <tr>
              <th scope="col">#</th>
              {columns.map((c) => (
                <th scope="col" key={c.key}>
                  {c.label}
                  {c.required ? " *" : ""}
                  {c.unit && <small>{c.unit}</small>}
                </th>
              ))}
              <th scope="col">
                <span className="w-table-sr">{t("tableActions")}</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index}>
                <th scope="row">{index + 1}</th>
                {columns.map((c) => {
                  const props = {
                    "aria-label": `${c.label} · ${t("tableRow")} ${index + 1}`,
                    disabled,
                  };
                  const cell = row[c.key] ?? "";
                  return (
                    <td key={c.key}>
                      {c.type === "select" ? (
                        <SelectControl
                          {...props}
                          value={cell}
                          onChange={(e) =>
                            setCell(index, c.key, e.target.value)
                          }
                        >
                          <option value="">{t("tableChoose")}</option>
                          {(c.options || []).map((x) => (
                            <option key={x}>{x}</option>
                          ))}
                        </SelectControl>
                      ) : c.type === "checkbox" ? (
                        <input
                          {...props}
                          type="checkbox"
                          checked={cell === true}
                          onChange={(e) =>
                            setCell(index, c.key, e.target.checked)
                          }
                        />
                      ) : c.type === "text" ? (
                        <textarea
                          {...props}
                          maxLength={1000}
                          value={cell}
                          onChange={(e) =>
                            setCell(index, c.key, e.target.value)
                          }
                        />
                      ) : (
                        <input
                          {...props}
                          type={
                            c.type === "number" || c.type === "date"
                              ? c.type
                              : "text"
                          }
                          step="any"
                          min={c.min ?? undefined}
                          max={c.max ?? undefined}
                          maxLength={1000}
                          value={cell}
                          onChange={(e) =>
                            setCell(
                              index,
                              c.key,
                              c.type === "number" && e.target.value !== ""
                                ? Number(e.target.value)
                                : e.target.value,
                            )
                          }
                        />
                      )}
                    </td>
                  );
                })}
                <td>
                  <button
                    type="button"
                    className="w-table-remove"
                    aria-label={`${t("tableRemoveRow")} ${index + 1}`}
                    onClick={() => onChange(rows.filter((_, i) => i !== index))}
                  >
                    {t("tableRemove")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && <p className="w-table-empty">{t("tableEmpty")}</p>}
      </div>
      <div className="w-table-footer">
        <button
          type="button"
          className="w-button secondary"
          disabled={disabled || rows.length >= (field.max_rows ?? 100)}
          onClick={() => onChange([...rows, {}])}
        >
          + {t("tableAddRow")}
        </button>
        <small>
          {rows.length} / {field.max_rows ?? 100} · {t("tableRows")}
          {field.min_rows > 0 && ` · ${t("tableMinimum")}: ${field.min_rows}`}
        </small>
      </div>
    </fieldset>
  );
}
