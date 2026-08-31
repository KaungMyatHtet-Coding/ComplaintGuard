"use client";

import Link from "next/link";
import { AppHeader } from "@/components/app-header";
import { useApp } from "@/components/app-provider";

export default function Home() {
  const { t } = useApp();
  const list = (key: "publicWhatItems" | "publicHowItems" | "publicWhyItems" | "publicPrivacyItems") => t(key).split("|");

  const services = [
    {
      title: t("landingServiceRoutingTitle"),
      description: t("landingServiceRoutingDescription"),
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"></path></svg>
      )
    },
    {
      title: t("landingServiceBilingualTitle"),
      description: t("landingServiceBilingualDescription"),
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129"></path></svg>
      )
    },
    {
      title: t("landingServiceSecurityTitle"),
      description: t("landingServiceSecurityDescription"),
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>
      )
    },
    {
      title: t("landingServiceReviewTitle"),
      description: t("landingServiceReviewDescription"),
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path></svg>
      )
    }
  ];

  const faqs = [
    {
      q: t("landingFaqWhatQuestion"),
      a: t("landingFaqWhatAnswer"),
    },
    {
      q: t("landingFaqWhoQuestion"),
      a: t("landingFaqWhoAnswer"),
    },
    {
      q: t("landingFaqSecurityQuestion"),
      a: t("landingFaqSecurityAnswer"),
    },
    {
      q: t("landingFaqClassificationQuestion"),
      a: t("landingFaqClassificationAnswer"),
    }
  ];

  return (
    <>
      <AppHeader />
      <main className="public-page w-full animate-fade-in flex flex-col">
        {/* Hero Section */}
        <section className="flex w-full min-h-[calc(100vh-4.5rem)] flex-col justify-center items-center px-6 sm:px-12 lg:px-24 xl:px-32 relative overflow-hidden bg-gray-950">
          <div 
            className="absolute inset-0 z-0 opacity-50 bg-cover bg-center"
            style={{ backgroundImage: "url('/bg-office.jpg')" }}
          ></div>
          <div className="absolute inset-0 z-0 bg-gradient-to-t from-gray-950 via-gray-950/70 to-transparent"></div>
          
          <div className="relative z-10 max-w-3xl w-full flex flex-col items-center px-4 sm:px-6">
            <p className="text-xs font-bold tracking-widest text-gray-300 uppercase mb-6">English · မြန်မာ</p>
            
            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold text-white tracking-tight leading-tight mb-6 text-center drop-shadow-lg">
              {t("tagline")}
            </h1>
            
            <p className="text-lg text-gray-200 mb-10 max-w-xl leading-relaxed text-center">
              {t("landingHeroLead")}
            </p>
            
            <div className="w-full h-px bg-gradient-to-r from-transparent via-white/20 to-transparent mb-10"></div>
            
            <div className="flex flex-col sm:flex-row items-center justify-center gap-5 w-full">
              <Link 
                href="/login" 
                className="public-action-primary group relative inline-flex items-center justify-center rounded-xl px-12 py-4 text-xl font-extrabold shadow-lg transition-all hover:shadow-[0_0_30px_rgba(255,255,255,0.4)] hover:-translate-y-0.5 focus:outline-none w-full sm:w-auto whitespace-nowrap"
              >
                <span>{t("signIn")}</span>
              </Link>
              <Link
                href="/register"
                className="public-action-secondary inline-flex w-full items-center justify-center rounded-xl border px-8 py-4 text-lg font-bold transition-all focus:outline-none sm:w-auto"
              >
                <span>{t("createAccount")}</span>
              </Link>
            </div>
          </div>
          
          {/* Scroll Down Indicator */}
          <div className="absolute bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 text-white/70 animate-bounce">
            <span className="text-xs font-semibold tracking-widest uppercase">{t("landingExplore")}</span>
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 14l-7 7m0 0l-7-7m7 7V3"></path></svg>
          </div>
        </section>

        <section className="public-surface-alt w-full px-6 py-20 sm:px-12 lg:px-24" aria-labelledby="what-title">
          <div className="mx-auto max-w-6xl">
            <h2 id="what-title" className="public-heading mb-10 text-center text-3xl font-extrabold tracking-tight md:text-4xl">{t("publicWhatTitle")}</h2>
            <ul className="public-list grid gap-5 md:grid-cols-2">
              {list("publicWhatItems").map((item) => <li key={item} className="public-card rounded-2xl border p-6 text-lg leading-relaxed">{item}</li>)}
            </ul>
          </div>
        </section>

        <section className="public-surface w-full px-6 py-20 sm:px-12 lg:px-24" aria-labelledby="how-title">
          <div className="mx-auto max-w-6xl">
            <h2 id="how-title" className="public-heading mb-10 text-center text-3xl font-extrabold tracking-tight md:text-4xl">{t("publicHowTitle")}</h2>
            <ol className="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
              {list("publicHowItems").map((item, index) => <li key={item} className="public-card rounded-2xl border p-6"><span className="mb-4 grid h-10 w-10 place-items-center rounded-full bg-[var(--action)] font-extrabold text-[var(--on-primary)]">{index + 1}</span><p className="public-heading font-bold leading-relaxed">{item}</p></li>)}
            </ol>
          </div>
        </section>

        <section className="public-surface-alt w-full px-6 py-20 sm:px-12 lg:px-24" aria-labelledby="why-title">
          <div className="mx-auto max-w-6xl">
            <h2 id="why-title" className="public-heading mb-10 text-center text-3xl font-extrabold tracking-tight md:text-4xl">{t("publicWhyTitle")}</h2>
            <ul className="public-list grid gap-x-10 gap-y-4 md:grid-cols-2 lg:grid-cols-3">
              {list("publicWhyItems").map((item) => <li key={item} className="list-disc pl-2 text-lg leading-relaxed">{item}</li>)}
            </ul>
          </div>
        </section>

        <section className="public-surface w-full px-6 py-20 sm:px-12 lg:px-24" aria-labelledby="oversight-title">
          <div className="mx-auto grid max-w-5xl gap-8 md:grid-cols-2">
            <div className="public-oversight rounded-2xl border-l-4 p-8" role="note">
              <h2 id="oversight-title" className="mb-4 text-2xl font-extrabold">{t("publicOversightTitle")}</h2>
              <p className="text-lg leading-relaxed">{t("publicOversight")}</p>
            </div>
            <div className="public-oversight rounded-2xl border-l-4 p-8" aria-labelledby="scope-title">
              <h2 id="scope-title" className="mb-4 text-2xl font-extrabold">{t("publicScopeTitle")}</h2>
              <p className="text-lg leading-relaxed">{t("publicScope")}</p>
            </div>
          </div>
        </section>

        <section className="public-surface-alt w-full px-6 py-20 sm:px-12 lg:px-24" aria-labelledby="privacy-title">
          <div className="mx-auto max-w-6xl">
            <h2 id="privacy-title" className="public-heading mb-10 text-center text-3xl font-extrabold tracking-tight md:text-4xl">{t("publicPrivacyTitle")}</h2>
            <ul className="public-list grid gap-5 md:grid-cols-2">
              {list("publicPrivacyItems").map((item) => <li key={item} className="public-card rounded-2xl border p-6 text-lg leading-relaxed">{item}</li>)}
            </ul>
          </div>
        </section>

        <section className="public-surface w-full px-6 py-20 sm:px-12 lg:px-24" aria-labelledby="cta-title">
          <div className="mx-auto max-w-3xl text-center">
            <h2 id="cta-title" className="public-heading mb-8 text-3xl font-extrabold tracking-tight md:text-4xl">{t("publicCtaTitle")}</h2>
            <div className="flex flex-col justify-center gap-4 sm:flex-row">
              <Link href="/login" className="primary-button sm:w-auto">{t("signIn")}</Link>
              <Link href="/register" className="inline-flex items-center justify-center rounded-xl border border-[var(--border)] px-6 py-3 font-bold text-[var(--text)] transition-colors hover:bg-[var(--surface-alt)]">{t("createAccount")}</Link>
            </div>
          </div>
        </section>

        {/* Existing service overview */}
        <section className="public-surface-alt w-full py-24 px-6 sm:px-12 lg:px-24">
          <div className="max-w-7xl mx-auto">
            <div className="text-center mb-16">
              <h2 className="public-heading text-3xl md:text-4xl font-extrabold mb-4 tracking-tight">{t("landingServicesTitle")}</h2>
              <p className="public-copy text-xl max-w-2xl mx-auto">{t("landingServicesLead")}</p>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8 lg:gap-12">
              {services.map((service, idx) => (
                <div key={idx} className="public-card rounded-3xl p-8 sm:p-10 shadow-sm border hover:shadow-xl transition-all duration-300 hover:-translate-y-1">
                  <div className="w-14 h-14 bg-black text-white rounded-2xl flex items-center justify-center mb-6 shadow-md">
                    {service.icon}
                  </div>
                  <h3 className="public-heading text-2xl font-bold mb-4">{service.title}</h3>
                  <p className="public-copy leading-relaxed text-lg">{service.description}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* FAQ Section */}
        <section className="public-surface w-full py-24 px-6 sm:px-12 lg:px-24">
          <div className="max-w-4xl mx-auto">
            <div className="text-center mb-16">
              <h2 className="public-heading text-3xl md:text-4xl font-extrabold mb-4 tracking-tight">{t("landingFaqTitle")}</h2>
              <p className="public-copy text-xl">{t("landingFaqLead")}</p>
            </div>

            <div className="space-y-6">
              {faqs.map((faq, idx) => (
                <div key={idx} className="public-card rounded-2xl p-6 md:p-8 border">
                  <h3 className="public-heading text-xl font-bold mb-3">{faq.q}</h3>
                  <p className="public-copy text-lg leading-relaxed">{faq.a}</p>
                </div>
              ))}
            </div>
          </div>
        </section>
        
        {/* Simple Footer */}
        <footer className="bg-gray-950 py-12 text-center border-t border-gray-900">
          <p className="text-gray-500 font-medium">© {new Date().getFullYear()} ComplaintGuard. All rights reserved.</p>
        </footer>
      </main>
    </>
  );
}
