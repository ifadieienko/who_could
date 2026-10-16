import en from "../locales/en.js";
import pl from "../locales/pl.js";
import ru from "../locales/ru.js";
const dictionaries = { en, pl, ru };
let current = "en";
export const supportedLocales = Object.keys(dictionaries);
// Reserved for reviewed translations; never advertised as production locales.
export const plannedLocales = ["de", "cs", "sk"];
export const localePreferenceKey = "who-could:locale";
export function readLocalePreference() {
  try {
    const value = localStorage.getItem(localePreferenceKey);
    return supportedLocales.includes(value) ? value : null;
  } catch {
    return null;
  }
}
export function saveLocalePreference(value) {
  try {
    localStorage.setItem(localePreferenceKey, value);
  } catch {
    /* Session-only if storage is blocked. */
  }
}
export function setLocale(locale) {
  current = dictionaries[locale] ? locale : "en";
}
export function t(key, locale = current) {
  return dictionaries[locale]?.[key] ?? dictionaries.en[key] ?? key;
}
