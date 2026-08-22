import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/app-provider", () => ({
  useApp: () => ({
    locale: "en",
    t: (key: string) => ({
      adminCustomer: "Customer",
      adminStaff: "Staff",
      adminManager: "Manager",
      adminRoleAdmin: "Admin",
      adminAccountDetailEyebrow: "Read-only account details",
      adminAccountDetailLead: "Only approved profile information is shown here.",
      adminAccountDetailClose: "Close details",
      adminAccountDetailStatusTitle: "Profile state and scope",
      adminDetailCustomerExplanation: "Publicly registered Customer profile. Department is not applicable.",
      adminDetailStaffExplanation: "Staff profile assigned to the displayed approved department.",
      adminDetailManagerExplanation: "Manager profile with no department assignment.",
      adminDetailAdminExplanation: "Administrative profile.",
      adminDetailProfileStateNote: "Profile state only.",
      adminDirectoryName: "Display name",
      adminEmail: "Email",
      adminRole: "Role",
      adminDepartment: "Department",
      adminDirectoryLanguage: "Language",
      adminDirectoryStatus: "Profile status",
      adminDirectoryActive: "Active",
      adminDirectoryPending: "Pending profile",
      adminNotApplicable: "Not applicable",
      adminDirectoryOwnerNotice: "Owner activation required",
      english: "English",
      myanmar: "Myanmar",
    }[key] ?? key),
  }),
}));

import { AdminAccountDetail } from "./admin-account-detail";

const refs = {
  openerRef: { current: null },
  fallbackRef: { current: null },
  canRestoreFocus: () => true,
};

function row(role: "customer" | "staff" | "manager" | "admin", active = true) {
  return {
    email: `${role}@example.test`,
    displayName: role,
    locale: "en" as const,
    role,
    departmentId: role === "staff" ? "card_atm" as const : null,
    active,
    setupStatus: active ? "active" as const : "pending_setup" as const,
  };
}

describe("AdminAccountDetail", () => {
  it("renders only approved safe fields with dialog semantics", () => {
    const markup = renderToStaticMarkup(<AdminAccountDetail row={row("staff")} {...refs} onClose={() => undefined} />);
    expect(markup).toContain('role="dialog"');
    expect(markup).toContain('aria-modal="true"');
    expect(markup).toContain('aria-labelledby="admin-account-detail-title"');
    expect(markup).not.toContain("card_atm");
    expect(markup).toContain("Staff");
    expect(markup).not.toContain("uid");
    expect(markup).not.toContain("createdAt");
    expect(markup).not.toContain("Auth");
    expect(markup).not.toContain("password");
    expect(markup).not.toContain("customerId");
  });

  it("uses Not applicable for non-Staff departments and safe role explanations", () => {
    const customerMarkup = renderToStaticMarkup(<AdminAccountDetail row={row("customer")} {...refs} onClose={() => undefined} />);
    const managerMarkup = renderToStaticMarkup(<AdminAccountDetail row={row("manager")} {...refs} onClose={() => undefined} />);
    expect(customerMarkup).toContain("Not applicable");
    expect(managerMarkup).toContain("Not applicable");
    expect(customerMarkup).toContain("Publicly registered Customer profile");
    expect(customerMarkup).not.toContain("Owner activation required");
  });

  it("limits activation wording to pending Staff and Manager profiles", () => {
    const staffMarkup = renderToStaticMarkup(<AdminAccountDetail row={row("staff", false)} {...refs} onClose={() => undefined} />);
    const adminMarkup = renderToStaticMarkup(<AdminAccountDetail row={row("admin", false)} {...refs} onClose={() => undefined} />);
    expect(staffMarkup).toContain("Owner activation required");
    expect(adminMarkup).not.toContain("Owner activation required");
  });
});
