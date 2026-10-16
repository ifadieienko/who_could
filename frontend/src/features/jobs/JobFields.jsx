import { SelectControl } from "../../components/workshop/SelectControl.jsx";
import { useEffect, useState } from "react";
import { call } from "../../repair-api.js";
import { Field, Button, ErrorBox } from "../../components/workshop/ui.jsx";
import { t } from "../../app/i18n.js";

export function PriorityField({ value, onChange, disabled }) {
  return (
    <Field label={t("jobPriority")}>
      <SelectControl
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      >
        {["low", "normal", "high", "urgent"].map((key) => (
          <option key={key} value={key}>
            {t("priority_" + key)}
          </option>
        ))}
      </SelectControl>
    </Field>
  );
}

export function RelatedPicker({ kind, customerId, value, onChange, disabled }) {
  const [query, setQuery] = useState(""),
    [after, setAfter] = useState(null),
    [items, setItems] = useState([]),
    [next, setNext] = useState(null),
    [selected, setSelected] = useState(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    if (!customerId) return;
    setBusy(true);
    setError("");
    const params = new URLSearchParams({ customer_id: customerId });
    if (kind === "assets") params.set("q", query);
    if (after) params.set("after", after);
    call(`/v2/${kind}?${params}`)
      .then((data) => {
        if (!active) return;
        setItems((old) => (after ? [...old, ...data.items] : data.items));
        setNext(data.next);
      })
      .catch((e) => active && setError(e.message))
      .finally(() => active && setBusy(false));
    return () => {
      active = false;
    };
  }, [kind, customerId, query, after]);
  useEffect(() => {
    let active = true;
    setSelected(null);
    if (value)
      call(`/v2/${kind}/${value}`)
        .then((row) => {
          if (active && row.customer_id === customerId) setSelected(row);
        })
        .catch((e) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [kind, value, customerId]);
  const options =
    selected && !items.some((row) => row.id === selected.id)
      ? [selected, ...items]
      : items;
  return (
    <>
      <ErrorBox error={error} />
      {kind === "assets" && (
        <Field label={t("jobAssetSearch")}>
          <input
            value={query}
            disabled={disabled}
            onChange={(e) => {
              setQuery(e.target.value);
              setAfter(null);
            }}
          />
        </Field>
      )}
      <Field label={t(kind === "assets" ? "jobAsset" : "jobSite")}>
        <SelectControl
          required={kind === "assets"}
          value={value || ""}
          disabled={disabled || busy || !customerId}
          onChange={(e) => onChange(Number(e.target.value) || null)}
        >
          <option value="">
            {t(kind === "assets" ? "jobChooseAsset" : "noSite")}
          </option>
          {value && !options.some((row) => row.id === value) && (
            <option value={value}>#{value}</option>
          )}
          {options.map((row) => (
            <option key={row.id} value={row.id}>
              {row.name || row.model}
              {row.serial ? ` · ${row.serial}` : ""}
            </option>
          ))}
        </SelectControl>
      </Field>
      {next && (
        <Button
          type="button"
          secondary
          disabled={disabled || busy}
          onClick={() => setAfter(next)}
        >
          {t(kind === "assets" ? "jobMoreAssets" : "jobMoreSites")}
        </Button>
      )}
    </>
  );
}
