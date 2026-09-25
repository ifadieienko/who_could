import { useState } from "react";
import { call } from "../../repair-api.js";
import {
  Button,
  ErrorBox,
  Field,
  useAction,
} from "../../components/workshop/ui.jsx";

const copy = {
  en: {
    title: "Organization",
    name: "Name",
    locale: "Language",
    zone: "Time zone",
    currency: "Default currency",
    country: "Country (ISO code)",
    save: "Save settings",
    note: "Existing jobs keep their original currency. Dates are displayed in this time zone.",
  },
  pl: {
    title: "Organizacja",
    name: "Nazwa",
    locale: "Język",
    zone: "Strefa czasowa",
    currency: "Waluta domyślna",
    country: "Kraj (kod ISO)",
    save: "Zapisz ustawienia",
    note: "Istniejące zlecenia zachowują swoją walutę. Daty są wyświetlane w tej strefie czasowej.",
  },
  ru: {
    title: "Организация",
    name: "Название",
    locale: "Язык",
    zone: "Часовой пояс",
    currency: "Валюта по умолчанию",
    country: "Страна (код ISO)",
    save: "Сохранить настройки",
    note: "Существующие заказы сохраняют свою валюту. Даты отображаются в выбранном часовом поясе.",
  },
};
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
    t = copy[form.locale] || copy.en;
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
      <h1>{t.title}</h1>
      <ErrorBox error={action.error} />
      <Field label={t.name}>
        <input required maxLength={160} {...field("name")} />
      </Field>
      <Field label={t.locale}>
        <select {...field("locale")}>
          <option value="en">English</option>
          <option value="pl">Polski</option>
          <option value="ru">Русский</option>
        </select>
      </Field>
      <Field label={t.zone}>
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
      <Field label={t.currency}>
        <select {...field("currency")}>
          {["PLN", "EUR", "GBP", "CZK"].map((v) => (
            <option key={v}>{v}</option>
          ))}
        </select>
      </Field>
      <Field label={t.country}>
        <input
          required
          pattern="[A-Z]{2}"
          maxLength={2}
          {...field("country")}
        />
      </Field>
      <p>{t.note}</p>
      <Button disabled={action.busy}>{t.save}</Button>
    </form>
  );
}
