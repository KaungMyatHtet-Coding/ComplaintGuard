"use client";

import Link from "next/link";

import { useApp } from "@/components/app-provider";
import { LanguageSwitcher } from "@/components/language-switcher";

export function AppHeader() {
  const { profile, signOut, t } = useApp();
  return (
    <header className="flex items-center justify-between gap-4 px-4 sm:px-8 py-3 bg-white/90 backdrop-blur-md border-b border-gray-200 sticky top-0 z-50">
      <Link href="/" className="flex items-center gap-3 font-bold whitespace-nowrap">
        <div className="flex items-center justify-center w-9 h-9 rounded-lg bg-black text-white shrink-0">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          </svg>
        </div>
        <span className="hidden sm:inline-block text-lg">{t("brand")}</span>
      </Link>
      <div className="flex items-center gap-2 sm:gap-4 shrink-0">
        <LanguageSwitcher />
        {profile ? (
          <button className="flex items-center justify-center p-2 rounded-lg text-gray-500 hover:bg-gray-100 hover:text-black transition-colors shrink-0" type="button" onClick={() => void signOut()} aria-label={t("signOut")} title={t("signOut")}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
              <polyline points="16 17 21 12 16 7"></polyline>
              <line x1="21" y1="12" x2="9" y2="12"></line>
            </svg>
          </button>
        ) : null}
      </div>
    </header>
  );
}
