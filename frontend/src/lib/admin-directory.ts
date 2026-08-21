import { getFirebaseServices } from "./firebase";
import { isDepartmentId, type DepartmentId } from "./department-labels";
import { resolveLocalMlApiBaseUrl } from "./runtime-environment";

export type AdminDirectoryRole = "staff" | "manager";
export type AdminDirectoryFilters = {
  role?: AdminDirectoryRole;
  departmentId?: DepartmentId;
  active?: boolean;
  search?: string;
  pageSize?: number;
  cursor?: string;
};

export type AdminDirectoryRow = {
  email: string;
  displayName: string;
  locale: "en" | "my";
  role: AdminDirectoryRole;
  departmentId: DepartmentId | null;
  active: boolean;
  setupStatus: "pending_setup" | "active";
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
  | "unavailable"
  | "unexpected";

export class AdminDirectoryError extends Error {
  constructor(public readonly code: AdminDirectoryErrorCode) {
    super(code);
  }
}

export function validateAdminDirectoryFilters(value: unknown): AdminDirectoryFilters {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new AdminDirectoryError("validation");
  }
  const record = value as Record<string, unknown>;
  const allowed = new Set(["role", "departmentId", "active", "search", "pageSize", "cursor"]);
  if (Object.keys(record).some((key) => !allowed.has(key))) throw new AdminDirectoryError("validation");
  if (record.role !== undefined && record.role !== "staff" && record.role !== "manager") {
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
  if (record.role === "manager" && record.departmentId !== undefined) throw new AdminDirectoryError("validation");
  return {
    ...(record.role ? { role: record.role } : {}),
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
  if (status === 503) return "unavailable";
  return "unexpected";
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
    return (await response.json()) as AdminDirectoryResponse;
  } catch (error) {
    if (error instanceof AdminDirectoryError) throw error;
    throw new AdminDirectoryError("unavailable");
  }
}
