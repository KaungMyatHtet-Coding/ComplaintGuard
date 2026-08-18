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
      <main className="flex min-h-[calc(100vh-4.5rem)] bg-white animate-fade-in">
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
            <div className="mb-10 text-center lg:text-left">
              <h2 className="text-3xl font-extrabold text-gray-900 tracking-tight">{t("loginTitle")}</h2>
              <p className="mt-3 text-gray-500 font-medium">{t("loginLead")}</p>
            </div>

            {configurationMissing ? (
              <div className="mb-6 p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-800" role="alert">
                <strong className="block font-bold mb-1">{t("configMissing")}</strong>
                <span className="text-sm">{t("configHelp")}</span>
              </div>
            ) : null}
            
            {status === "error" ? (
              <div className="mb-6 p-4 rounded-xl bg-red-50 border border-red-200 text-red-800 font-medium text-sm" role="alert">
                {permissionError ? t("permissionError") : t("authError")}
              </div>
            ) : null}

            <form onSubmit={submit} noValidate className="space-y-5">
              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">{t("email")}</label>
                <input
                  type="email"
                  autoComplete="username"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  className="w-full px-4 py-3 rounded-xl border border-gray-300 focus:ring-2 focus:ring-black focus:border-black transition-all bg-gray-50 focus:bg-white text-gray-900 outline-none"
                  placeholder="name@example.com"
                />
              </div>

              <div>
                <label className="block text-sm font-bold text-gray-700 mb-2">{t("password")}</label>
                <input
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="w-full px-4 py-3 rounded-xl border border-gray-300 focus:ring-2 focus:ring-black focus:border-black transition-all bg-gray-50 focus:bg-white text-gray-900 outline-none"
                  placeholder="••••••••"
                />
              </div>

              <button 
                className="w-full flex justify-center py-3.5 px-4 border border-transparent rounded-xl shadow-sm text-sm font-bold text-white bg-black hover:bg-gray-900 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-black transition-all disabled:opacity-70 disabled:cursor-not-allowed mt-4" 
                disabled={isLoading || configurationMissing}
                suppressHydrationWarning
              >
                {isLoading ? t("signingIn") : t("signIn")}
              </button>
            </form>

            <div className="mt-8 pt-6 border-t border-gray-100">
              <p className="text-center text-xs font-medium text-gray-500 bg-gray-50 py-3 px-4 rounded-lg border border-gray-200">
                {t("demoHelp")}
              </p>
            </div>
          </div>
        </div>
      </main>
    </>
  );
}
