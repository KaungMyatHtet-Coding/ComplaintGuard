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
      >
        {t("english")}
      </button>
      <button
        type="button"
        aria-pressed={locale === "my"}
        onClick={() => setLocale("my")}
      >
        {t("myanmar")}
      </button>
    </fieldset>
  );
}
