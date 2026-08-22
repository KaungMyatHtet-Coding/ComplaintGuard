import { getFirebaseServices } from "./firebase";
import { isDepartmentId, type DepartmentId } from "./department-labels";
import { resolveLocalMlApiBaseUrl } from "./runtime-environment";

export type AdminDirectoryRole = "customer" | "staff" | "manager" | "admin";
export type AdminDirectoryFilters = {
  role?: AdminDirectoryRole;
  departmentId?: DepartmentId;
  active?: boolean;
  search?: string;
  pageSize?: number;
  cursor?: string;
};

export type AdminDirectoryRow = {
  accountRef: string;
  email: string;
  displayName: string;
  locale: "en" | "my";
  role: AdminDirectoryRole;
  departmentId: DepartmentId | null;
  active: boolean;
  setupStatus: "pending_setup" | "active";
};

export type LifecycleEligibilityReason =
  | "already_active"
  | "already_inactive"
  | "self_target_forbidden"
  | "last_active_admin"
  | "role_not_reassignable"
  | "assigned_unresolved_work"
  | "pending_setup_activation_forbidden";

export type LifecycleEligibilityOperation = {
  eligible: boolean;
  reason: LifecycleEligibilityReason | null;
};

export type AdminLifecycleEligibility = {
  accountRef: string;
  profileState: "active" | "inactive";
  operations: {
    disable: LifecycleEligibilityOperation;
    reactivate: LifecycleEligibilityOperation;
    reassignDepartment: LifecycleEligibilityOperation;
  };
};

export type AdminDirectoryResponse = {
  rows: AdminDirectoryRow[];
  nextCursor: string | null;
  hasMore: boolean;
};

export type AdminDirectoryErrorCode =
  | "authentication"
  | "permission"
  | "validation"
  | "notFound"
  | "unavailable"
  | "unexpected";

export class AdminDirectoryError extends Error {
  constructor(public readonly code: AdminDirectoryErrorCode) {
    super(code);
  }
}

const roles = new Set<AdminDirectoryRole>(["customer", "staff", "manager", "admin"]);
const setupStatuses = new Set(["pending_setup", "active"]);
const emailPattern = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
const accountReferencePattern = /^acct_v1_[0-9a-f]{64}$/;
const eligibilityReasons = new Set<LifecycleEligibilityReason>([
  "already_active",
  "already_inactive",
  "self_target_forbidden",
  "last_active_admin",
  "role_not_reassignable",
  "assigned_unresolved_work",
  "pending_setup_activation_forbidden",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function parseRow(value: unknown): AdminDirectoryRow {
  if (!isRecord(value) || Object.keys(value).length !== 8) throw new AdminDirectoryError("validation");
  const { accountRef, email, displayName, locale, role, departmentId, active, setupStatus } = value;
  if (
    typeof accountRef !== "string" || !accountReferencePattern.test(accountRef) ||
    typeof email !== "string" || email !== email.trim().toLowerCase() || !emailPattern.test(email) || email.length > 254 ||
    typeof displayName !== "string" || displayName !== displayName.trim() || !displayName || displayName.length > 100 ||
    (locale !== "en" && locale !== "my") ||
    (typeof role !== "string" || !roles.has(role as AdminDirectoryRole)) ||
    (departmentId !== null && typeof departmentId !== "string" && departmentId !== undefined) ||
    typeof active !== "boolean" ||
    typeof setupStatus !== "string" || !setupStatuses.has(setupStatus)
  ) throw new AdminDirectoryError("validation");
  if (role === "staff" && !isDepartmentId(departmentId as string)) throw new AdminDirectoryError("validation");
  if (role !== "staff" && departmentId !== null) throw new AdminDirectoryError("validation");
  if ((active && setupStatus !== "active") || (!active && setupStatus !== "pending_setup")) throw new AdminDirectoryError("validation");
  return { accountRef, email, displayName, locale, role: role as AdminDirectoryRole, departmentId: departmentId as DepartmentId | null, active, setupStatus: setupStatus as AdminDirectoryRow["setupStatus"] };
}

function parseEligibilityOperation(value: unknown): LifecycleEligibilityOperation {
  if (!isRecord(value) || Object.keys(value).length !== 2 || typeof value.eligible !== "boolean") throw new AdminDirectoryError("validation");
  if (value.reason !== null && (typeof value.reason !== "string" || !eligibilityReasons.has(value.reason as LifecycleEligibilityReason))) throw new AdminDirectoryError("validation");
  return { eligible: value.eligible, reason: value.reason as LifecycleEligibilityReason | null };
}

export function parseAdminLifecycleEligibility(value: unknown): AdminLifecycleEligibility {
  if (!isRecord(value) || Object.keys(value).length !== 3 || typeof value.accountRef !== "string" || !accountReferencePattern.test(value.accountRef) || (value.profileState !== "active" && value.profileState !== "inactive") || !isRecord(value.operations) || Object.keys(value.operations).length !== 3) throw new AdminDirectoryError("validation");
  const operations = value.operations;
  if (!("disable" in operations) || !("reactivate" in operations) || !("reassignDepartment" in operations)) throw new AdminDirectoryError("validation");
  return {
    accountRef: value.accountRef,
    profileState: value.profileState,
    operations: {
      disable: parseEligibilityOperation(operations.disable),
      reactivate: parseEligibilityOperation(operations.reactivate),
      reassignDepartment: parseEligibilityOperation(operations.reassignDepartment),
    },
  };
}

export function parseAdminDirectoryResponse(value: unknown): AdminDirectoryResponse {
  if (!isRecord(value) || Object.keys(value).length !== 3 || !Array.isArray(value.rows)) throw new AdminDirectoryError("validation");
  if (typeof value.nextCursor !== "string" && value.nextCursor !== null) throw new AdminDirectoryError("validation");
  if (typeof value.nextCursor === "string" && (!value.nextCursor || value.nextCursor.length > 128)) throw new AdminDirectoryError("validation");
  if (typeof value.hasMore !== "boolean") throw new AdminDirectoryError("validation");
  const rows = value.rows.map(parseRow);
  if (value.hasMore !== (value.nextCursor !== null)) throw new AdminDirectoryError("validation");
  return { rows, nextCursor: value.nextCursor, hasMore: value.hasMore };
}

export function validateAdminDirectoryFilters(value: unknown): AdminDirectoryFilters {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new AdminDirectoryError("validation");
  }
  const record = value as Record<string, unknown>;
  const allowed = new Set(["role", "departmentId", "active", "search", "pageSize", "cursor"]);
  if (Object.keys(record).some((key) => !allowed.has(key))) throw new AdminDirectoryError("validation");
  if (record.role !== undefined && !roles.has(record.role as AdminDirectoryRole)) {
    throw new AdminDirectoryError("validation");
  }
  if (record.departmentId !== undefined && !isDepartmentId(record.departmentId as string)) {
    throw new AdminDirectoryError("validation");
  }
  if (record.active !== undefined && typeof record.active !== "boolean") {
    throw new AdminDirectoryError("validation");
  }
  const search = record.search === undefined ? undefined : typeof record.search === "string" ? record.search.trim() : null;
  if (search === null || (search !== undefined && (!search || search.length > 80))) {
    throw new AdminDirectoryError("validation");
  }
  if (record.pageSize !== undefined && (!Number.isInteger(record.pageSize) || (record.pageSize as number) < 1 || (record.pageSize as number) > 50)) {
    throw new AdminDirectoryError("validation");
  }
  if (record.cursor !== undefined && (typeof record.cursor !== "string" || !record.cursor || record.cursor.length > 128)) {
    throw new AdminDirectoryError("validation");
  }
  if (record.role !== "staff" && record.departmentId !== undefined) throw new AdminDirectoryError("validation");
  return {
    ...(record.role ? { role: record.role as AdminDirectoryRole } : {}),
    ...(record.departmentId ? { departmentId: record.departmentId as DepartmentId } : {}),
    ...(record.active !== undefined ? { active: record.active } : {}),
    ...(search ? { search } : {}),
    ...(record.pageSize !== undefined ? { pageSize: record.pageSize as number } : {}),
    ...(record.cursor ? { cursor: record.cursor } : {}),
  };
}

function mapStatus(status: number): AdminDirectoryErrorCode {
  if (status === 401) return "authentication";
  if (status === 403) return "permission";
  if (status === 422) return "validation";
  if (status === 404) return "notFound";
  if (status === 503) return "unavailable";
  return "unexpected";
}

export async function loadAdminLifecycleEligibility(
  accountRef: string,
  fetcher: typeof fetch = fetch,
): Promise<AdminLifecycleEligibility> {
  if (!accountReferencePattern.test(accountRef)) throw new AdminDirectoryError("validation");
  let apiBase: string;
  try {
    apiBase = resolveLocalMlApiBaseUrl();
  } catch {
    throw new AdminDirectoryError("unavailable");
  }
  let user;
  try {
    user = getFirebaseServices().auth.currentUser;
  } catch {
    throw new AdminDirectoryError("unavailable");
  }
  if (!user) throw new AdminDirectoryError("authentication");
  let token: string;
  try {
    token = await user.getIdToken(true);
  } catch {
    throw new AdminDirectoryError("authentication");
  }
  if (!token) throw new AdminDirectoryError("authentication");
  try {
    const response = await fetcher(`${apiBase}/admin/users/${encodeURIComponent(accountRef)}/lifecycle-eligibility`, {
      method: "GET",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) throw new AdminDirectoryError(mapStatus(response.status));
    return parseAdminLifecycleEligibility(await response.json());
  } catch (error) {
    if (error instanceof AdminDirectoryError) throw error;
    throw new AdminDirectoryError("unavailable");
  }
}

export async function loadAdminDirectory(
  value: unknown = {},
  fetcher: typeof fetch = fetch,
): Promise<AdminDirectoryResponse> {
  let filters: AdminDirectoryFilters;
  let apiBase: string;
  try {
    filters = validateAdminDirectoryFilters(value);
    apiBase = resolveLocalMlApiBaseUrl();
  } catch (error) {
    if (error instanceof AdminDirectoryError) throw error;
    throw new AdminDirectoryError("unavailable");
  }
  let user;
  try {
    user = getFirebaseServices().auth.currentUser;
  } catch {
    throw new AdminDirectoryError("unavailable");
  }
  if (!user) throw new AdminDirectoryError("authentication");
  let token: string;
  try {
    token = await user.getIdToken(true);
  } catch {
    throw new AdminDirectoryError("authentication");
  }
  if (!token) throw new AdminDirectoryError("authentication");
  const params = new URLSearchParams();
  if (filters.role) params.set("role", filters.role);
  if (filters.departmentId) params.set("departmentId", filters.departmentId);
  if (filters.active !== undefined) params.set("active", String(filters.active));
  if (filters.search) params.set("search", filters.search);
  if (filters.pageSize !== undefined) params.set("pageSize", String(filters.pageSize));
  if (filters.cursor) params.set("cursor", filters.cursor);
  try {
    const response = await fetcher(`${apiBase}/admin/users?${params.toString()}`, {
      method: "GET",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) throw new AdminDirectoryError(mapStatus(response.status));
    return parseAdminDirectoryResponse(await response.json());
  } catch (error) {
    if (error instanceof AdminDirectoryError) throw error;
    throw new AdminDirectoryError("unavailable");
  }
}
