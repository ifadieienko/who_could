import { SelectControl } from "../../components/workshop/SelectControl.jsx";
import { t } from "../../app/i18n.js";

const size = (node) =>
  node == null
    ? 0
    : 1 +
      (node.all || node.any || []).reduce(
        (total, child) => total + size(child),
        0,
      );
export function ConditionEditor({ value, onChange, fields }) {
  const available = fields.filter(
    (f) => !f.condition && !["table", "image"].includes(f.type),
  );
  const fresh = () => ({
    field: available[0]?.key || "",
    operator: "equals",
    value:
      available[0]?.type === "checkbox"
        ? true
        : available[0]?.type === "number"
          ? 0
          : "",
  });
  const total = size(value);
  const render = (node, change, depth = 0) => {
    const group = node.all ? "all" : node.any ? "any" : null;
    const source = available.find((f) => f.key === node.field);
    const operator = node.operator || "equals";
    const operand = node.operator ? node.value : node.equals;
    const operators = [
      "equals",
      "not_equals",
      ...(source?.type === "number"
        ? ["gt", "gte", "lt", "lte"]
        : ["string", "text", "select"].includes(source?.type)
          ? ["contains"]
          : []),
      "is_empty",
    ];
    const leaf = (patch) => {
      const next = {
        field: node.field,
        operator,
        ...(operator === "is_empty" ? {} : { value: operand }),
        ...patch,
      };
      if (next.operator === "is_empty") delete next.value;
      change(next);
    };
    return (
      <div className="w-condition-node">
        {group ? (
          <>
            <SelectControl
              aria-label={t("conditionLogic")}
              value={group}
              onChange={(e) => change({ [e.target.value]: node[group] })}
            >
              <option value="all">{t("conditionAll")}</option>
              <option value="any">{t("conditionAny")}</option>
            </SelectControl>
            {node[group].map((child, i) => (
              <div key={i}>
                {render(
                  child,
                  (next) => {
                    const children = node[group].flatMap((c, n) =>
                      n === i ? (next ? [next] : []) : [c],
                    );
                    change(children.length ? { [group]: children } : null);
                  },
                  depth + 1,
                )}
              </div>
            ))}
            <div className="w-actions">
              <button
                type="button"
                disabled={total >= 20 || node[group].length >= 10}
                onClick={() => change({ [group]: [...node[group], fresh()] })}
              >
                {t("conditionAddRule")}
              </button>
              {depth < 2 && (
                <button
                  type="button"
                  disabled={total >= 19 || node[group].length >= 10}
                  onClick={() =>
                    change({ [group]: [...node[group], { all: [fresh()] }] })
                  }
                >
                  {t("conditionAddGroup")}
                </button>
              )}
            </div>
          </>
        ) : (
          <div className="w-condition-rule">
            <SelectControl
              aria-label={t("conditionField")}
              value={node.field}
              onChange={(e) => {
                const f = available.find((x) => x.key === e.target.value);
                change({
                  field: f.key,
                  operator: "equals",
                  value:
                    f.type === "checkbox" ? true : f.type === "number" ? 0 : "",
                });
              }}
            >
              {!source && <option value={node.field}>{node.field}</option>}
              {available.map((f) => (
                <option key={f.key} value={f.key}>
                  {f.label || f.key}
                </option>
              ))}
            </SelectControl>
            <SelectControl
              aria-label={t("conditionOperator")}
              value={operator}
              onChange={(e) =>
                leaf({
                  operator: e.target.value,
                  value:
                    operand ??
                    (source?.type === "number"
                      ? 0
                      : source?.type === "checkbox"
                        ? true
                        : ""),
                })
              }
            >
              {operators.map((op) => (
                <option key={op} value={op}>
                  {t("condition_" + op)}
                </option>
              ))}
            </SelectControl>
            {operator !== "is_empty" &&
              (source?.type === "checkbox" ? (
                <SelectControl
                  aria-label={t("conditionValue")}
                  value={String(operand)}
                  onChange={(e) => leaf({ value: e.target.value === "true" })}
                >
                  <option value="true">{t("conditionYes")}</option>
                  <option value="false">{t("conditionNo")}</option>
                </SelectControl>
              ) : (
                <input
                  aria-label={t("conditionValue")}
                  type={
                    source?.type === "number"
                      ? "number"
                      : source?.type === "date"
                        ? "date"
                        : "text"
                  }
                  step="any"
                  required={source?.type === "number"}
                  maxLength={1000}
                  value={operand ?? ""}
                  onChange={(e) =>
                    leaf({
                      value:
                        source?.type === "number" && e.target.value !== ""
                          ? Number(e.target.value)
                          : e.target.value,
                    })
                  }
                />
              ))}
          </div>
        )}
        <button
          type="button"
          className="w-condition-remove"
          onClick={() => change(null)}
        >
          {t("conditionRemove")}
        </button>
      </div>
    );
  };
  return (
    <section className="w-condition-editor" aria-label={t("conditionTitle")}>
      <h4>{t("conditionTitle")}</h4>
      {value ? (
        <>
          {render(value, onChange)}
          {!value.all && !value.any && (
            <button type="button" onClick={() => onChange({ all: [value] })}>
              {t("conditionCombine")}
            </button>
          )}
        </>
      ) : (
        <button
          type="button"
          disabled={!available.length}
          onClick={() => onChange(fresh())}
        >
          {t("conditionAdd")}
        </button>
      )}
      <small>{t("conditionHelp")}</small>
    </section>
  );
}
