import { useEffect, useState } from "react";
import { Popover } from "@base-ui/react/popover";
import { Palette, Sun, Moon, Monitor, Check } from "lucide-react";
import { t } from "./i18n.js";
const key = "who-could:appearance";
const themes = ["light", "dark", "system"];
const colors = { green: 145, red: 4, violet: 270, blue: 215, amber: 35 };
function read() {
  try {
    const p = JSON.parse(localStorage.getItem(key));
    return {
      theme: themes.includes(p?.theme) ? p.theme : "light",
      accent: Object.hasOwn(colors, p?.accent) ? p.accent : "green",
    };
  } catch {
    return { theme: "light", accent: "green" };
  }
}
function apply(p) {
  const dark =
    p.theme === "dark" ||
    (p.theme === "system" &&
      window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  document.documentElement.dataset.accent = p.accent;
  document.documentElement.style.setProperty("--hue", colors[p.accent]);
}
apply(read());
export function Appearance() {
  const [prefs, setPrefs] = useState(read);
  useEffect(() => {
    apply(prefs);
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const change = () => apply(prefs);
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, [prefs]);
  const update = (patch) => {
    const next = { ...prefs, ...patch };
    apply(next);
    setPrefs(next);
    try {
      localStorage.setItem(key, JSON.stringify(next));
    } catch {}
  };
  return (
    <Popover.Root>
      <Popover.Trigger
        className="w-appearance-trigger"
        aria-label={t("appearance")}
        title={t("appearance")}
      >
        <Palette size={18} aria-hidden="true" />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner
          sideOffset={10}
          align="end"
          className="w-appearance-positioner"
        >
          <Popover.Popup className="w-appearance-popup">
            <Popover.Title className="w-appearance-title">
              {t("appearance")}
            </Popover.Title>
            <fieldset>
              <legend>{t("theme")}</legend>
              <div className="w-theme-options">
                {themes.map((theme, i) => {
                  const Icon = [Sun, Moon, Monitor][i];
                  return (
                    <label key={theme} className="w-theme-choice">
                      <input
                        type="radio"
                        name="appearance-theme"
                        value={theme}
                        checked={prefs.theme === theme}
                        onChange={() => update({ theme })}
                      />
                      <span>
                        <Icon size={17} aria-hidden="true" />
                        {t("theme_" + theme)}
                      </span>
                    </label>
                  );
                })}
              </div>
            </fieldset>
            <fieldset>
              <legend>{t("accent")}</legend>
              <div className="w-color-options">
                {Object.entries(colors).map(([accent, hue]) => (
                  <label
                    key={accent}
                    className="w-color-choice"
                    style={{ "--swatch": `hsl(${hue} 55% 45%)` }}
                  >
                    <input
                      type="radio"
                      name="appearance-accent"
                      value={accent}
                      aria-label={t("accent_" + accent)}
                      checked={prefs.accent === accent}
                      onChange={() => update({ accent })}
                    />
                    <span title={t("accent_" + accent)}>
                      <Check size={17} aria-hidden="true" />
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  );
}
