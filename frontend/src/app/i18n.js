import en from "../locales/en.js";
import pl from "../locales/pl.js";
import ru from "../locales/ru.js";
const dictionaries = { en, pl, ru };
let current = "en";
export const supportedLocales = Object.keys(dictionaries);
// Reserved for reviewed translations; never advertised as production locales.
export const plannedLocales = ["de", "cs", "sk"];
export function setLocale(locale) {
  current = dictionaries[locale] ? locale : "en";
}
export function t(key, locale = current) {
  return dictionaries[locale]?.[key] ?? dictionaries.en[key] ?? key;
}
