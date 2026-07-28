"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { AppHeader } from "@/components/app-header";
import { useApp } from "@/components/app-provider";
import { roleDestinations } from "@/lib/auth-policy";

export default function LoginPage() {
  const router = useRouter();
  const { errorCode, profile, signIn, status, t } = useApp();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  useEffect(() => {
    if (profile && status === "authenticated") {
      router.replace(roleDestinations[profile.role]);
    }
  }, [profile, router, status]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await signIn(email, password);
  }

  const configurationMissing = status === "configuration_missing";
  const isLoading = status === "loading";
  const permissionError = errorCode?.startsWith("profile_");

  return (
    <>
      <AppHeader />
      <main className="auth-layout">
        <section className="auth-intro">
          <p className="eyebrow">Secure access foundation</p>
          <h1>{t("tagline")}</h1>
          <p>{t("sensitiveWarning")}</p>
          <div className="security-note">{t("securityBoundary")}</div>
        </section>
        <section className="auth-card">
          <h2>{t("loginTitle")}</h2>
          <p>{t("loginLead")}</p>
          {configurationMissing ? (
            <div className="error-panel" role="alert">
              <strong>{t("configMissing")}</strong>
              <span>{t("configHelp")}</span>
            </div>
          ) : null}
          {status === "error" ? (
            <div className="error-panel" role="alert">
              {permissionError ? t("permissionError") : t("authError")}
            </div>
          ) : null}
          <form onSubmit={submit} noValidate>
            <label>
              {t("email")}
              <input
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </label>
            <label>
              {t("password")}
              <input
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            <button className="primary-button" disabled={isLoading || configurationMissing}>
              {isLoading ? t("signingIn") : t("signIn")}
            </button>
          </form>
          <p className="demo-note">{t("demoHelp")}</p>
        </section>
      </main>
    </>
  );
}
