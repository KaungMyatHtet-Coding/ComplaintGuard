"use client";

import Link from "next/link";

import { useApp } from "@/components/app-provider";
import { LanguageSwitcher } from "@/components/language-switcher";

export function AppHeader() {
  const { profile, signOut, t } = useApp();
  return (
    <header className="site-header">
      <Link href="/" className="brand">
        <span className="brand-mark">CG</span>
        <span>{t("brand")}</span>
      </Link>
      <div className="header-actions">
        {profile ? <span className="role-chip">{profile.role}</span> : null}
        <LanguageSwitcher />
        {profile ? (
          <button className="text-button" type="button" onClick={() => void signOut()}>
            {t("signOut")}
          </button>
        ) : null}
      </div>
    </header>
  );
}
