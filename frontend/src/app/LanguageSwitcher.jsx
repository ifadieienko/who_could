import { supportedLocales, t } from "./i18n.js";
const names = { en: "English", pl: "Polski", ru: "Русский" };
export function LanguageSwitcher({ locale, onChange }) {
  return (
    <header className="w-global-bar">
      <label className="w-language">
        <span>{t("locale")}</span>
        <select
          aria-label="Language / Язык / Język"
          value={locale}
          onChange={(e) => onChange(e.target.value)}
        >
          {supportedLocales.map((code) => (
            <option key={code} value={code} lang={code}>
              {names[code]}
            </option>
          ))}
        </select>
      </label>
    </header>
  );
}
