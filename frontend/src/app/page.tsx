"use client";

import Link from "next/link";

import { AppHeader } from "@/components/app-header";
import { useApp } from "@/components/app-provider";

export default function Home() {
  const { t } = useApp();
  return (
    <>
      <AppHeader />
      <main className="hero">
        <section>
          <p className="eyebrow">English · မြန်မာ</p>
          <h1>{t("tagline")}</h1>
          <p>{t("foundationOnly")}</p>
          <Link className="primary-button inline-button" href="/login">
            {t("signIn")}
          </Link>
        </section>
        <aside className="hero-card">
          <span className="hero-icon">✓</span>
          <strong>{t("securityBoundary")}</strong>
          <p>{t("sensitiveWarning")}</p>
        </aside>
      </main>
    </>
  );
}
