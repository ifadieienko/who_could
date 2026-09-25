import { useState } from "react";
import { call } from "../../repair-api.js";
import {
  Button,
  ErrorBox,
  Field,
  useAction,
} from "../../components/workshop/ui.jsx";

import { t } from "../../app/i18n.js";
export function OrganizationSettings({ shop, onSave }) {
  const [form, setForm] = useState(() =>
    Object.fromEntries(
      [
        "name",
        "locale",
        "timezone",
        "currency",
        "country",
        "settings",
        "version",
      ].map((k) => [k, shop[k]]),
    ),
  );
  const action = useAction(),
    tr = (key) => t(key, form.locale);
  const field = (key) => ({
    value: form[key],
    onChange: (e) => setForm({ ...form, [key]: e.target.value }),
  });
  return (
    <form
      className="w-panel"
      onSubmit={(e) => {
        e.preventDefault();
        action.run(async () => {
          const result = await call("/v2/organization", {
            method: "PATCH",
            body: form,
          });
          setForm({ ...form, version: result.version });
          await onSave();
        });
      }}
    >
      <h1>{tr("organization")}</h1>
      <ErrorBox error={action.error} />
      <Field label={tr("name")}>
        <input required maxLength={160} {...field("name")} />
      </Field>
      <Field label={tr("locale")}>
        <select {...field("locale")}>
          <option value="en">English</option>
          <option value="pl">Polski</option>
          <option value="ru">Русский</option>
        </select>
      </Field>
      <Field label={tr("timezone")}>
        <input required list="timezones" {...field("timezone")} />
        <datalist id="timezones">
          {[
            "Europe/Warsaw",
            "Europe/London",
            "Europe/Prague",
            "Europe/Berlin",
            "Europe/Bratislava",
            "UTC",
          ].map((v) => (
            <option key={v} value={v} />
          ))}
        </datalist>
      </Field>
      <Field label={tr("currency")}>
        <select {...field("currency")}>
          {["PLN", "EUR", "GBP", "CZK"].map((v) => (
            <option key={v}>{v}</option>
          ))}
        </select>
      </Field>
      <Field label={tr("country")}>
        <input
          required
          pattern="[A-Z]{2}"
          maxLength={2}
          {...field("country")}
        />
      </Field>
      <p>{tr("regionalNote")}</p>
      <Button disabled={action.busy}>{tr("saveSettings")}</Button>
    </form>
  );
}
