import { Globe2 } from "lucide-react";
import { supportedLocales, t } from "./i18n.js";
const names = { en: "English", pl: "Polski", ru: "Русский" };
export function LanguageSwitcher({ locale, onChange }) {
  return (
    <header className="w-global-bar">
      <div className="w-header-signature" aria-label="Who Could">
        <span aria-hidden="true">w.</span> WHO COULD
        <span className="w-header-dot" aria-hidden="true" />
      </div>
      <label className="w-language">
        <Globe2 size={16} strokeWidth={1.6} aria-hidden="true" />
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
