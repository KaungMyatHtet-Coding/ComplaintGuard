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
      adminDirectoryState_active: "Active",
      adminDirectoryState_pending_setup: "Pending setup",
      adminDirectoryState_disabled: "Disabled",
      adminDirectoryState_inactive_unverified: "Inactive status unavailable",
      adminDetailStateActive: "Active account.",
      adminDetailStatePending: "Staff or Manager profile awaiting trusted owner activation.",
      adminDetailStateDisabled: "Account intentionally disabled; reactivation is a separate lifecycle operation.",
      adminDetailStateUnavailable: "Inactive account state is unavailable; no lifecycle meaning is inferred.",
      adminNotApplicable: "Not applicable",
      adminDirectoryOwnerNotice: "Owner activation required",
      english: "English",
      myanmar: "Myanmar",
    }[key] ?? key),
  }),
}));

import { AdminAccountDetail, isFreshDisableTarget, isFreshReactivateEligible, isFreshReactivateRecoveryCompatible, isFreshReactivateTarget } from "./admin-account-detail";

type AccountState = "active" | "pending_setup" | "disabled" | "inactive_unverified";

const refs = {
  openerRef: { current: null },
  fallbackRef: { current: null },
  canRestoreFocus: () => true,
};

function row(role: "customer" | "staff" | "manager" | "admin", active = true, accountState: AccountState = active ? "active" : "pending_setup") {
  return {
    accountRef: "acct_v1_0000000000000000000000000000000000000000000000000000000000000000",
    email: `${role}@example.test`,
    displayName: role,
    locale: "en" as const,
    role,
    departmentId: role === "staff" ? "card_atm" as const : null,
    active,
    accountState,
  };
}

describe("AdminAccountDetail", () => {
  it("renders only approved safe fields with dialog semantics", () => {
    const markup = renderToStaticMarkup(<AdminAccountDetail row={row("staff")} {...refs} onClose={() => undefined} />);
    expect(markup).toContain('role="dialog"');
    expect(markup).toContain('aria-modal="true"');
    expect(markup).toContain('aria-labelledby="admin-account-detail-title"');
    expect(markup).toContain('aria-labelledby="admin-account-detail-management-title"');
    expect(markup).toContain("adminLifecycleManagementTitle");
    expect(markup).toContain('role="status"');
    expect(markup).not.toContain("Continue");
    expect(markup).not.toContain("lifecycle-recovery");
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

  it("keeps disabled and unavailable states distinct from pending setup", () => {
    const disabledMarkup = renderToStaticMarkup(<AdminAccountDetail row={row("staff", false, "disabled")} {...refs} onClose={() => undefined} />);
    const unavailableMarkup = renderToStaticMarkup(<AdminAccountDetail row={row("customer", false, "inactive_unverified")} {...refs} onClose={() => undefined} />);
    expect(disabledMarkup).toContain("Disabled");
    expect(disabledMarkup).not.toContain("Owner activation required");
    expect(unavailableMarkup).toContain("Inactive status unavailable");
    expect(unavailableMarkup).not.toContain("Owner activation required");
  });

  it("gates fresh Disable targets on active account state and supported role", () => {
    expect(isFreshDisableTarget(row("customer"))).toBe(true);
    expect(isFreshDisableTarget(row("staff"))).toBe(true);
    expect(isFreshDisableTarget(row("staff", false, "disabled"))).toBe(false);
    expect(isFreshDisableTarget(row("staff", false, "pending_setup"))).toBe(false);
    expect(isFreshDisableTarget(row("customer", false, "inactive_unverified"))).toBe(false);
    expect(isFreshDisableTarget(row("admin"))).toBe(false);
  });

  it("gates fresh Reactivate targets on disabled state and supported non-Admin roles", () => {
    expect(isFreshReactivateTarget(row("customer", false, "disabled"))).toBe(true);
    expect(isFreshReactivateTarget(row("staff", false, "disabled"))).toBe(true);
    expect(isFreshReactivateTarget(row("manager", false, "disabled"))).toBe(true);
    expect(isFreshReactivateTarget(row("customer", true, "active"))).toBe(false);
    expect(isFreshReactivateTarget(row("customer", false, "pending_setup"))).toBe(false);
    expect(isFreshReactivateTarget(row("customer", false, "inactive_unverified"))).toBe(false);
    expect(isFreshReactivateTarget(row("admin", false, "disabled"))).toBe(false);
  });

  it("rejects contradictory loaded eligibility for Reactivate", () => {
    const disabled = row("customer", false, "disabled");
    const base = {
      accountRef: disabled.accountRef,
      profileState: "inactive" as const,
      operations: {
        disable: { eligible: false, reason: "already_inactive" as const },
        reactivate: { eligible: true, reason: null },
        reassignDepartment: { eligible: false, reason: "role_not_reassignable" as const },
      },
    };
    expect(isFreshReactivateEligible(disabled, base)).toBe(true);
    expect(isFreshReactivateEligible(disabled, { ...base, profileState: "active" })).toBe(false);
    expect(isFreshReactivateEligible(disabled, { ...base, operations: { ...base.operations, reactivate: { eligible: false, reason: "already_inactive" } } })).toBe(false);
  });

  it("accepts only completed Disable lineage or no recovery for a fresh Reactivate", () => {
    expect(isFreshReactivateRecoveryCompatible({ accountRef: row("customer").accountRef, recoveryState: "none", operation: null, departmentId: null })).toBe(true);
    expect(isFreshReactivateRecoveryCompatible({ accountRef: row("customer").accountRef, recoveryState: "completed", operation: "disable", departmentId: null })).toBe(true);
    expect(isFreshReactivateRecoveryCompatible({ accountRef: row("customer").accountRef, recoveryState: "completed", operation: "reactivate", departmentId: null })).toBe(false);
    expect(isFreshReactivateRecoveryCompatible({ accountRef: row("customer").accountRef, recoveryState: "completed", operation: "reassign_department", departmentId: "card_atm" })).toBe(false);
    expect(isFreshReactivateRecoveryCompatible({ accountRef: row("customer").accountRef, recoveryState: "recoverable", operation: "disable", departmentId: null })).toBe(false);
    expect(isFreshReactivateRecoveryCompatible({ accountRef: row("customer").accountRef, recoveryState: "operator_required", operation: null, departmentId: null })).toBe(false);
  });
});
