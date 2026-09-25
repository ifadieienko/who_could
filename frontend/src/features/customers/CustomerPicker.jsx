import { useEffect, useState } from "react";
import { call } from "../../repair-api.js";
import { Field, ErrorBox } from "../../components/workshop/ui.jsx";
import { t } from "../../app/i18n.js";
export function CustomerPicker({ value, onChange, disabled }) {
  const [query, setQuery] = useState(""),
    [items, setItems] = useState([]),
    [selected, setSelected] = useState(null),
    [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    call("/v2/customer-records?q=" + encodeURIComponent(query))
      .then((data) => {
        if (active) setItems(data.items);
      })
      .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [query]);
  useEffect(() => {
    let active = true;
    if (value)
      call("/v2/customer-records/" + value)
        .then((data) => active && setSelected(data))
        .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [value]);
  const options =
    selected && !items.some((x) => x.id === selected.id)
      ? [selected, ...items]
      : items;
  return (
    <>
      <ErrorBox error={error} />
      <Field label={t("selectCustomer")}>
        <input
          disabled={disabled}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </Field>
      <Field label={t("customer")}>
        <select
          required
          disabled={disabled}
          value={value || ""}
          onChange={(e) => onChange(Number(e.target.value))}
        >
          <option value="">—</option>
          {options.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
              {c.company_name ? " · " + c.company_name : ""}
            </option>
          ))}
        </select>
      </Field>
    </>
  );
}
