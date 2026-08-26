"use client";

import { useEffect, useRef, useState } from "react";

import { useApp } from "@/components/app-provider";

export const themePreferences = ["system", "light", "dark"] as const;
export type ThemePreference = (typeof themePreferences)[number];

const storageKey = "complaintguard.theme";

export function readThemePreference(storage: Pick<Storage, "getItem"> | null): ThemePreference {
  try {
    const value = storage?.getItem(storageKey);
    return themePreferences.includes(value as ThemePreference) ? value as ThemePreference : "system";
  } catch {
    return "system";
  }
}

export function applyThemePreference(preference: ThemePreference, root: HTMLElement): void {
  root.dataset.theme = preference;
}

export function ThemeControl() {
  const { t } = useApp();
  const [preference, setPreference] = useState<ThemePreference>("system");
  const preferenceRef = useRef<ThemePreference>("system");

  useEffect(() => {
    const stored = readThemePreference(window.localStorage);
    preferenceRef.current = stored;
    queueMicrotask(() => setPreference(stored));
    applyThemePreference(stored, document.documentElement);

    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onSystemThemeChange = () => {
      if (preferenceRef.current === "system") applyThemePreference("system", document.documentElement);
    };
    media.addEventListener?.("change", onSystemThemeChange);
    return () => media.removeEventListener?.("change", onSystemThemeChange);
  }, []);

  function changePreference(next: ThemePreference) {
    setPreference(next);
    preferenceRef.current = next;
    applyThemePreference(next, document.documentElement);
    try {
      window.localStorage.setItem(storageKey, next);
    } catch {
      // Theme remains usable for the current session when storage is unavailable.
    }
  }

  return (
    <label className="theme-control">
      <span className="sr-only">{t("themeLabel")}</span>
      <select aria-label={t("themeLabel")} value={preference} onChange={(event) => changePreference(event.target.value as ThemePreference)}>
        <option value="system">{t("themeSystem")}</option>
        <option value="light">{t("themeLight")}</option>
        <option value="dark">{t("themeDark")}</option>
      </select>
    </label>
  );
}
