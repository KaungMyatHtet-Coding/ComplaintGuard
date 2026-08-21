import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: ReactNode; href: string }) => <a href={href}>{children}</a>,
}));

vi.mock("@/components/app-header", () => ({ AppHeader: () => null }));

vi.mock("@/components/app-provider", () => ({
  useApp: () => ({
    t: (key: string) => ({
      tagline: "Bilingual financial complaint routing",
      landingHeroLead: "Submit a complaint and follow its progress.",
      landingExplore: "Explore",
      landingServicesTitle: "How ComplaintGuard helps",
      landingServicesLead: "Support for financial complaints.",
      landingServiceRoutingTitle: "Assisted complaint routing",
      landingServiceRoutingDescription: "Supports complaint classification and routing.",
      landingServiceBilingualTitle: "Bilingual support",
      landingServiceBilingualDescription: "Use English or Myanmar.",
      landingServiceSecurityTitle: "Privacy-minded access",
      landingServiceSecurityDescription: "Role-based access protects information.",
      landingServiceReviewTitle: "Manager review when needed",
      landingServiceReviewDescription: "Uncertain cases can be reviewed.",
      landingFaqTitle: "Frequently asked questions",
      landingFaqLead: "Simple answers.",
      landingFaqWhatQuestion: "What is ComplaintGuard?",
      landingFaqWhatAnswer: "A secure complaint platform.",
      landingFaqWhoQuestion: "Who handles my complaint?",
      landingFaqWhoAnswer: "The appropriate team reviews it.",
      landingFaqSecurityQuestion: "How is my complaint handled?",
      landingFaqSecurityAnswer: "Role-based access is used.",
      landingFaqClassificationQuestion: "How does complaint routing work?",
      landingFaqClassificationAnswer: "Uncertain cases receive review.",
      signIn: "Sign in",
      createAccount: "Create an account",
    }[key] ?? key),
  }),
}));

import Home from "./page";

describe("landing page customer-facing copy", () => {
  it("uses approachable localized keys without internal authorization or absolute-routing claims", () => {
    const markup = renderToStaticMarkup(<Home />);
    expect(markup).toContain("Assisted complaint routing");
    expect(markup).toContain("Frequently asked questions");
    expect(markup).not.toContain("Firestore rules");
    expect(markup).not.toContain("trusted backend");
    expect(markup).not.toContain("Never enter a PIN");
    expect(markup).not.toContain("zero misroutings");
    expect(markup).not.toContain("exact right department");
    expect(markup).not.toContain("Instantly categorizes");
  });
});
