"use client";

import Link from "next/link";
import { AppHeader } from "@/components/app-header";
import { useApp } from "@/components/app-provider";

export default function Home() {
  const { t } = useApp();

  const services = [
    {
      title: "Automated ML Routing",
      description: "Instantly categorizes and routes your financial complaints to the exact right department using advanced Machine Learning algorithms.",
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"></path></svg>
      )
    },
    {
      title: "Bilingual Support",
      description: "Full platform accessibility in both English and Myanmar, ensuring a seamless experience for a diverse user base.",
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129"></path></svg>
      )
    },
    {
      title: "Role-Based Security",
      description: "Enterprise-grade security rules ensure that Customers, Staff, and Managers only access the data they are authorized to see.",
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>
      )
    },
    {
      title: "Human-in-the-Loop Review",
      description: "Complex cases that the AI is unsure about are automatically flagged for manual review by managers, ensuring zero misroutings.",
      icon: (
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path></svg>
      )
    }
  ];

  const faqs = [
    {
      q: "What is ComplaintGuard?",
      a: "A secure, AI-powered platform for submitting, tracking, and resolving financial complaints quickly and efficiently."
    },
    {
      q: "Who handles my complaint?",
      a: "Upon submission, your ticket is instantly routed to a specialized department expert (e.g., Fraud & Security, Loans & Credit) based on your description."
    },
    {
      q: "Is my sensitive data secure?",
      a: "Yes. We enforce strict data boundaries so only authorized department staff can view your dispute. (Please remember never to submit full passwords or PINs)."
    },
    {
      q: "How does the AI classification work?",
      a: "We use a highly trained NLP model to analyze the text of your complaint, predicting the most appropriate resolution department in milliseconds."
    }
  ];

  return (
    <>
      <AppHeader />
      <main className="w-full bg-white animate-fade-in flex flex-col">
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
              {t("sensitiveWarning")}
            </p>
            
            <div className="w-full h-px bg-gradient-to-r from-transparent via-white/20 to-transparent mb-10"></div>
            
            <div className="flex flex-col sm:flex-row items-center justify-center gap-5 w-full">
              <div className="inline-flex items-center gap-2 px-5 py-3.5 bg-black/50 rounded-xl border border-white/10 text-sm font-medium text-gray-200">
                <svg className="w-5 h-5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>
                {t("securityBoundary")}
              </div>
              
              <Link 
                href="/login" 
                className="group relative inline-flex items-center justify-center rounded-xl bg-white px-12 py-4 text-xl font-extrabold text-gray-900 shadow-lg transition-all hover:bg-gray-100 hover:shadow-[0_0_30px_rgba(255,255,255,0.4)] hover:-translate-y-0.5 focus:outline-none w-full sm:w-auto whitespace-nowrap"
              >
                <span>{t("signIn")}</span>
              </Link>
            </div>
          </div>
          
          {/* Scroll Down Indicator */}
          <div className="absolute bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 text-white/70 animate-bounce">
            <span className="text-xs font-semibold tracking-widest uppercase">Explore</span>
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 14l-7 7m0 0l-7-7m7 7V3"></path></svg>
          </div>
        </section>

        {/* Services Section */}
        <section className="w-full py-24 bg-[#f6f7ed] px-6 sm:px-12 lg:px-24">
          <div className="max-w-7xl mx-auto">
            <div className="text-center mb-16">
              <h2 className="text-3xl md:text-4xl font-extrabold text-gray-900 mb-4 tracking-tight">Core Platform Services</h2>
              <p className="text-xl text-gray-500 max-w-2xl mx-auto">Powered by advanced Machine Learning, ComplaintGuard streamlines financial dispute resolution.</p>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8 lg:gap-12">
              {services.map((service, idx) => (
                <div key={idx} className="bg-white rounded-3xl p-8 sm:p-10 shadow-sm border border-gray-100 hover:shadow-xl transition-all duration-300 hover:-translate-y-1">
                  <div className="w-14 h-14 bg-black text-white rounded-2xl flex items-center justify-center mb-6 shadow-md">
                    {service.icon}
                  </div>
                  <h3 className="text-2xl font-bold text-gray-900 mb-4">{service.title}</h3>
                  <p className="text-gray-600 leading-relaxed text-lg">{service.description}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* FAQ Section */}
        <section className="w-full py-24 bg-white px-6 sm:px-12 lg:px-24">
          <div className="max-w-4xl mx-auto">
            <div className="text-center mb-16">
              <h2 className="text-3xl md:text-4xl font-extrabold text-gray-900 mb-4 tracking-tight">Frequently Asked Questions</h2>
              <p className="text-xl text-gray-500">Everything you need to know about how ComplaintGuard protects and routes your data.</p>
            </div>

            <div className="space-y-6">
              {faqs.map((faq, idx) => (
                <div key={idx} className="bg-[#f6f7ed] rounded-2xl p-6 md:p-8 border border-gray-100">
                  <h4 className="text-xl font-bold text-gray-900 mb-3">{faq.q}</h4>
                  <p className="text-gray-600 text-lg leading-relaxed">{faq.a}</p>
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
