"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";

import { AppHeader } from "@/components/app-header";
import { useApp } from "@/components/app-provider";
import { roleDestinations } from "@/lib/auth-policy";

export default function LoginPage() {
  const router = useRouter();
  const { errorCode, profile, signIn, status, t } = useApp();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const errorSummaryRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (profile && status === "authenticated") {
      router.replace(roleDestinations[profile.role]);
    }
  }, [profile, router, status]);

  useEffect(() => {
    if (status === "error" || status === "configuration_missing") {
      window.requestAnimationFrame(() => errorSummaryRef.current?.focus());
    }
  }, [status]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await signIn(email, password);
  }

  const configurationMissing = status === "configuration_missing";
  const isLoading = status === "loading";
  const permissionError = errorCode?.startsWith("profile_");
  const profileIncomplete = status === "profile_incomplete";

  return (
    <>
      <AppHeader />
      <main className="auth-page flex min-h-[calc(100vh-4.5rem)] animate-fade-in">
        {/* Left Side: Intro & Branding */}
        <div className="hidden lg:flex lg:w-1/2 flex-col justify-center px-12 xl:px-24 relative overflow-hidden bg-gray-950">
          <div 
            className="absolute inset-0 z-0 opacity-50 bg-cover bg-center"
            style={{ backgroundImage: "url('/bg-office.jpg')" }}
          ></div>
          <div className="absolute inset-0 z-0 bg-gradient-to-t from-gray-950 via-gray-950/70 to-transparent"></div>
          
          <div className="relative z-10">
            <p className="text-xs font-bold tracking-widest text-gray-400 uppercase mb-4">Secure access foundation</p>
            <h1 className="text-4xl xl:text-5xl font-extrabold text-white tracking-tight leading-tight mb-6 drop-shadow-md">
              {t("tagline")}
            </h1>
            <p className="text-lg text-gray-300 mb-8 max-w-lg leading-relaxed drop-shadow-sm">
              {t("sensitiveWarning")}
            </p>
            <div className="inline-flex items-center gap-2 px-4 py-2 bg-black/40 backdrop-blur-md rounded-full border border-gray-700/50 text-sm font-medium text-gray-200 shadow-xl">
              <svg className="w-4 h-4 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>
              {t("securityBoundary")}
            </div>
          </div>
        </div>

        {/* Right Side: Login Form */}
        <div className="flex-1 flex flex-col justify-center px-4 sm:px-6 lg:px-20 xl:px-24 py-12">
          <div className="mx-auto w-full max-w-sm lg:max-w-md animate-slide-up-fade">
            <nav className="auth-navigation" aria-label={t("authenticationNavigation")}>
              <Link href="/" className="auth-home-link">← {t("backToHome")}</Link>
            </nav>
            <div className="mb-10 text-center lg:text-left">
              <h2 className="auth-heading text-3xl font-extrabold tracking-tight">{t("loginTitle")}</h2>
              <p className="auth-lead mt-3 font-medium">{t("loginLead")}</p>
            </div>

            {configurationMissing ? (
              <div ref={errorSummaryRef} tabIndex={-1} className="auth-error-summary mb-6 rounded-xl border p-4 text-sm" role="alert">
                <strong className="block font-bold mb-1">{t("configMissing")}</strong>
                <span className="text-sm">{t("configHelp")}</span>
              </div>
            ) : null}
            
            {status === "error" ? (
              <div ref={errorSummaryRef} tabIndex={-1} className="auth-error-summary mb-6 rounded-xl border p-4 text-sm font-medium" role="alert">
                {permissionError ? t("permissionError") : t("authError")}
              </div>
            ) : null}

            {profileIncomplete ? (
              <div className="mb-6 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900" role="status">
                <strong className="block font-bold">{t("setupIncomplete")}</strong>
                <Link href="/register" className="mt-2 inline-block font-bold underline underline-offset-4">{t("finishSetup")}</Link>
              </div>
            ) : null}

            <form onSubmit={submit} noValidate className="space-y-5">
              <div>
              <label htmlFor="login-email" className="auth-label block text-sm font-bold mb-2">{t("email")}</label>
              <input
                id="login-email"
                name="email"
                  type="email"
                  autoComplete="username"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  className="auth-input"
                  placeholder="name@example.com"
                />
              </div>

              <div>
              <label htmlFor="login-password" className="auth-label block text-sm font-bold mb-2">{t("password")}</label>
              <div className="auth-password-row">
              <input
                id="login-password"
                name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="auth-input"
                  placeholder="••••••••"
                />
                <button type="button" className="auth-password-toggle" aria-label={showPassword ? t("hidePassword") : t("showPassword")} onClick={() => setShowPassword((value) => !value)}>
                  {showPassword ? t("hidePassword") : t("showPassword")}
                </button>
              </div>
              </div>

              <button 
                className="auth-submit mt-4"
                disabled={isLoading || configurationMissing}
                suppressHydrationWarning
              >
                {isLoading ? t("signingIn") : t("signIn")}
              </button>
            </form>

            <div className="auth-secondary mt-6 text-center text-sm">
              <span>{t("registerLead")} </span>
              <Link href="/register" className="font-bold underline underline-offset-4">
                {t("createAccount")}
              </Link>
            </div>

            <div className="mt-8 border-t border-[var(--border)] pt-6">
              <p className="auth-help rounded-lg border border-[var(--border)] bg-[var(--surface-alt)] px-4 py-3 text-center text-xs font-medium">
                {t("demoHelp")}
              </p>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
