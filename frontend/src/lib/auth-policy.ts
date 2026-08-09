export const roles = ["customer", "staff", "manager", "admin"] as const;

export type AppRole = (typeof roles)[number];

export type UserProfile = {
  uid: string;
  displayName: string;
  email: string;
  role: AppRole;
  departmentId: string | null;
  locale: "en" | "my";
  active: boolean;
};

export const roleDestinations: Record<AppRole, string> = {
  customer: "/dashboard",
  staff: "/dashboard",
  manager: "/dashboard",
  admin: "/dashboard",
};

export const roleNavigation: Record<AppRole, readonly string[]> = {
  customer: ["dashboard"],
  staff: ["dashboard"],
  manager: ["dashboard"],
  admin: ["dashboard"],
};

export function isAppRole(value: unknown): value is AppRole {
  return typeof value === "string" && roles.includes(value as AppRole);
}

export function canViewManagerAnalytics(role: AppRole): boolean {
  return role === "manager";
}

export function validateCredentials(email: string, password: string) {
  const normalizedEmail = email.trim();
  if (!normalizedEmail || !normalizedEmail.includes("@")) {
    return { valid: false as const, code: "invalid_email" };
  }
  if (!password) {
    return { valid: false as const, code: "missing_password" };
  }
  return { valid: true as const, email: normalizedEmail };
}

export function parseUserProfile(
  uid: string,
  email: string,
  value: unknown,
): UserProfile {
  if (!value || typeof value !== "object") {
    throw new Error("profile_missing");
  }
  const record = value as Record<string, unknown>;
  if (!isAppRole(record.role) || record.active !== true) {
    throw new Error("profile_unauthorized");
  }
  const locale = record.locale === "my" ? "my" : "en";
  const departmentId =
    typeof record.departmentId === "string" && record.departmentId.trim()
      ? record.departmentId
      : null;
  if (record.role === "staff" && !departmentId) {
    throw new Error("profile_department_missing");
  }
  return {
    uid,
    email,
    displayName:
      typeof record.displayName === "string" && record.displayName.trim()
        ? record.displayName.trim()
        : email,
    role: record.role,
    departmentId,
    locale,
    active: true,
  };
}
