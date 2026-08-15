"use client";

import { useApp } from "@/components/app-provider";

export function LanguageSwitcher() {
  const { locale, setLocale, t } = useApp();
  return (
    <fieldset className="language-switcher" aria-label={t("language")}>
      <legend className="sr-only">{t("language")}</legend>
      <button
        type="button"
        aria-pressed={locale === "en"}
        onClick={() => setLocale("en")}
        title={t("english")}
      >
        <span aria-hidden="true">🇺🇸</span>
        <span className="sr-only">{t("english")}</span>
      </button>
      <button
        type="button"
        aria-pressed={locale === "my"}
        onClick={() => setLocale("my")}
        title={t("myanmar")}
      >
        <span aria-hidden="true">🇲🇲</span>
        <span className="sr-only">{t("myanmar")}</span>
      </button>
    </fieldset>
  );
}
