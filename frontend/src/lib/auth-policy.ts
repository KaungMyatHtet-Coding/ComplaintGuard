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

export type ProfileResolution =
  | { kind: "missing" }
  | { kind: "valid"; profile: UserProfile }
  | { kind: "inactive" }
  | { kind: "malformed" };

const departmentIds = new Set([
  "transfer_payment",
  "account_support",
  "card_atm",
  "fraud_security",
  "loan_credit",
  "general_support",
]);

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

export function parseUserProfileStrict(
  uid: string,
  email: string,
  value: unknown,
): UserProfile {
  if (!value || typeof value !== "object") throw new Error("profile_malformed");
  const record = value as Record<string, unknown>;
  if (
    record.email !== email ||
    typeof record.displayName !== "string" ||
    !record.displayName.trim() ||
    (record.locale !== "en" && record.locale !== "my") ||
    !isAppRole(record.role) ||
    typeof record.active !== "boolean" ||
    record.createdAt == null ||
    record.updatedAt == null
  ) {
    throw new Error("profile_malformed");
  }
  if (
    record.departmentId !== null &&
    (typeof record.departmentId !== "string" ||
      !departmentIds.has(record.departmentId))
  ) {
    throw new Error("profile_malformed");
  }
  if (record.role === "staff" && !record.departmentId) {
    throw new Error("profile_malformed");
  }
  if (record.role !== "staff" && record.departmentId !== null) {
    throw new Error("profile_malformed");
  }
  if (record.active !== true) throw new Error("profile_inactive");
  return {
    uid,
    email,
    displayName: record.displayName.trim(),
    role: record.role,
    departmentId: record.departmentId,
    locale: record.locale,
    active: true,
  };
}

export function resolveUserProfile(
  uid: string,
  email: string,
  exists: boolean,
  value: unknown,
): ProfileResolution {
  if (!exists) return { kind: "missing" };
  try {
    return {
      kind: "valid",
      profile: parseUserProfileStrict(uid, email, value),
    };
  } catch (error) {
    if (error instanceof Error && error.message === "profile_inactive") {
      return { kind: "inactive" };
    }
    return { kind: "malformed" };
  }
}
