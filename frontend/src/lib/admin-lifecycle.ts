import { getFirebaseServices } from "./firebase";
import {
  accountReferencePattern,
  AdminDirectoryError,
  type AdminDirectoryErrorCode,
  hasExactKeys,
} from "./admin-directory";
import { isDepartmentId, type DepartmentId } from "./department-labels";
import { resolveLocalMlApiBaseUrl } from "./runtime-environment";

export type AdminLifecycleRecoveryState =
  | "none"
  | "recoverable"
  | "completed"
  | "operator_required";

export type AdminLifecycleRecoveryOperation =
  | "disable"
  | "reactivate"
  | "reassign_department";

export type AdminLifecycleRecoveryStatus = {
  accountRef: string;
  recoveryState: AdminLifecycleRecoveryState;
  operation: AdminLifecycleRecoveryOperation | null;
  departmentId: DepartmentId | null;
};

export type AdminDisableResult = {
  accountRef: string;
  operation: "disable";
  status: "completed";
  profileState: "inactive";
};

export type AdminReactivateResult = {
  accountRef: string;
  operation: "reactivate";
  status: "completed";
  profileState: "active";
};

export type AdminReassignDepartmentResult = {
  accountRef: string;
  operation: "reassign_department";
  status: "completed";
  departmentId: DepartmentId;
};

export type AdminLifecycleRequestOutcome = "definitive" | "unknown";

export type AdminLifecycleSafeErrorCode =
  | "assigned_unresolved_work"
  | "department_unchanged"
  | "idempotency_conflict"
  | "lifecycle_conflict"
  | "operator_recovery_required"
  | "recovery_operation_mismatch"
  | "role_not_reassignable"
  | "admin_reassign_not_available";

export class AdminLifecycleRequestError extends AdminDirectoryError {
  constructor(
    code: AdminDirectoryErrorCode,
    public readonly outcome: AdminLifecycleRequestOutcome,
    public readonly httpStatus?: number,
    public readonly safeErrorCode?: AdminLifecycleSafeErrorCode,
  ) {
    super(code);
  }
}

const safeErrorCodes = new Set<AdminLifecycleSafeErrorCode>([
  "assigned_unresolved_work",
  "department_unchanged",
  "idempotency_conflict",
  "lifecycle_conflict",
  "operator_recovery_required",
  "recovery_operation_mismatch",
  "role_not_reassignable",
  "admin_reassign_not_available",
]);

async function parseSafeErrorCode(response: Response): Promise<AdminLifecycleSafeErrorCode | undefined> {
  try {
    const value: unknown = await response.json();
    if (!hasExactKeys(value, ["error"]) || !hasExactKeys(value.error, ["code", "message", "details"])) return undefined;
    if (typeof value.error.code !== "string" || typeof value.error.message !== "string" || !Array.isArray(value.error.details)) return undefined;
    return safeErrorCodes.has(value.error.code as AdminLifecycleSafeErrorCode)
      ? value.error.code as AdminLifecycleSafeErrorCode
      : undefined;
  } catch {
    return undefined;
  }
}

const recoveryStates = new Set<AdminLifecycleRecoveryState>([
  "none",
  "recoverable",
  "completed",
  "operator_required",
]);
const recoveryOperations = new Set<AdminLifecycleRecoveryOperation>([
  "disable",
  "reactivate",
  "reassign_department",
]);
const idempotencyKeyPattern = /^[A-Za-z0-9_-]{8,64}$/;
const idempotencyAlphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-";

export function parseAdminLifecycleRecoveryStatus(
  value: unknown,
): AdminLifecycleRecoveryStatus {
  if (!hasExactKeys(value, ["accountRef", "recoveryState", "operation", "departmentId"])) {
    throw new AdminDirectoryError("validation");
  }
  const { accountRef, recoveryState, operation, departmentId } = value;
  if (
    typeof accountRef !== "string" ||
    !accountReferencePattern.test(accountRef) ||
    typeof recoveryState !== "string" ||
    !recoveryStates.has(recoveryState as AdminLifecycleRecoveryState) ||
    (operation !== null &&
      (typeof operation !== "string" ||
        !recoveryOperations.has(operation as AdminLifecycleRecoveryOperation))) ||
    (departmentId !== null &&
      (typeof departmentId !== "string" || !isDepartmentId(departmentId)))
  ) {
    throw new AdminDirectoryError("validation");
  }

  const safeState = recoveryState as AdminLifecycleRecoveryState;
  const safeOperation = operation as AdminLifecycleRecoveryOperation | null;
  const safeDepartment = departmentId as DepartmentId | null;
  if (safeState === "none" || safeState === "operator_required") {
    if (safeOperation !== null || safeDepartment !== null) {
      throw new AdminDirectoryError("validation");
    }
  } else if (safeOperation === null) {
    throw new AdminDirectoryError("validation");
  } else if (safeOperation === "reassign_department") {
    if (safeDepartment === null) throw new AdminDirectoryError("validation");
  } else if (safeDepartment !== null) {
    throw new AdminDirectoryError("validation");
  }

  return {
    accountRef,
    recoveryState: safeState,
    operation: safeOperation,
    departmentId: safeDepartment,
  };
}

export function parseAdminDisableResult(value: unknown): AdminDisableResult {
  if (!hasExactKeys(value, ["accountRef", "operation", "status", "profileState"])) {
    throw new AdminDirectoryError("validation");
  }
  if (
    typeof value.accountRef !== "string" ||
    !accountReferencePattern.test(value.accountRef) ||
    value.operation !== "disable" ||
    value.status !== "completed" ||
    value.profileState !== "inactive"
  ) {
    throw new AdminDirectoryError("validation");
  }
  return {
    accountRef: value.accountRef,
    operation: "disable",
    status: "completed",
    profileState: "inactive",
  };
}

export function parseAdminReactivateResult(value: unknown): AdminReactivateResult {
  if (!hasExactKeys(value, ["accountRef", "operation", "status", "profileState"])) {
    throw new AdminDirectoryError("validation");
  }
  if (
    typeof value.accountRef !== "string" ||
    !accountReferencePattern.test(value.accountRef) ||
    value.operation !== "reactivate" ||
    value.status !== "completed" ||
    value.profileState !== "active"
  ) {
    throw new AdminDirectoryError("validation");
  }
  return {
    accountRef: value.accountRef,
    operation: "reactivate",
    status: "completed",
    profileState: "active",
  };
}

export function parseAdminReassignDepartmentResult(value: unknown, requestedDepartmentId: DepartmentId): AdminReassignDepartmentResult {
  if (!hasExactKeys(value, ["accountRef", "operation", "status", "departmentId"])) {
    throw new AdminDirectoryError("validation");
  }
  if (
    typeof value.accountRef !== "string" ||
    !accountReferencePattern.test(value.accountRef) ||
    value.operation !== "reassign_department" ||
    value.status !== "completed" ||
    typeof value.departmentId !== "string" ||
    !isDepartmentId(value.departmentId) ||
    value.departmentId !== requestedDepartmentId
  ) {
    throw new AdminDirectoryError("validation");
  }
  return {
    accountRef: value.accountRef,
    operation: "reassign_department",
    status: "completed",
    departmentId: requestedDepartmentId,
  };
}

export function generateAdminLifecycleIdempotencyKey(): string {
  const cryptoApi = globalThis.crypto;
  if (!cryptoApi || typeof cryptoApi.getRandomValues !== "function") {
    throw new AdminDirectoryError("unavailable");
  }
  const bytes = new Uint8Array(32);
  cryptoApi.getRandomValues(bytes);
  return Array.from(bytes, (byte) => idempotencyAlphabet[byte % idempotencyAlphabet.length]).join("");
}

function validateIdempotencyKey(value: string): void {
  if (typeof value !== "string" || !idempotencyKeyPattern.test(value)) {
    throw new AdminDirectoryError("validation");
  }
}

function mapStatus(status: number): AdminDirectoryErrorCode {
  if (status === 401) return "authentication";
  if (status === 403) return "permission";
  if (status === 404) return "notFound";
  if (status === 422) return "validation";
  if (status === 503) return "unavailable";
  return "unexpected";
}

async function postAdminLifecycle(
  accountRef: string,
  body: Record<string, string>,
  endpoint: "disable" | "reactivate" | "reassign-department" | "lifecycle-recovery",
  operation: "disable" | "reactivate" | "reassign_department",
  requestedDepartmentId: DepartmentId | undefined,
  fetcher: typeof fetch,
  signal: AbortSignal | undefined,
): Promise<AdminDisableResult | AdminReactivateResult | AdminReassignDepartmentResult> {
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

  let response: Response;
  try {
    response = await fetcher(
      `${apiBase}/admin/users/${encodeURIComponent(accountRef)}/${endpoint}`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
        signal,
      },
    );
  } catch {
    throw new AdminLifecycleRequestError("unavailable", "unknown");
  }
  if (!response.ok) {
    const safeErrorCode = await parseSafeErrorCode(response);
    throw new AdminLifecycleRequestError(mapStatus(response.status), "definitive", response.status, safeErrorCode);
  }
  try {
    const parsed = operation === "disable"
      ? parseAdminDisableResult(await response.json())
      : operation === "reactivate"
        ? parseAdminReactivateResult(await response.json())
        : parseAdminReassignDepartmentResult(await response.json(), requestedDepartmentId as DepartmentId);
    if (parsed.accountRef !== accountRef) throw new AdminDirectoryError("validation");
    return parsed;
  } catch (error) {
    if (error instanceof AdminDirectoryError && error.code === "validation") {
      throw new AdminLifecycleRequestError("validation", "unknown");
    }
    throw new AdminLifecycleRequestError("unavailable", "unknown");
  }
}

export async function disableAdminAccount(
  accountRef: string,
  idempotencyKey: string,
  fetcher: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<AdminDisableResult> {
  validateIdempotencyKey(idempotencyKey);
  return postAdminLifecycle(accountRef, { idempotencyKey }, "disable", "disable", undefined, fetcher, signal) as Promise<AdminDisableResult>;
}

export async function continueAdminDisable(
  accountRef: string,
  fetcher: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<AdminDisableResult> {
  return postAdminLifecycle(
    accountRef,
    { operation: "disable" },
    "lifecycle-recovery",
    "disable",
    undefined,
    fetcher,
    signal,
  ) as Promise<AdminDisableResult>;
}

export async function reactivateAdminAccount(
  accountRef: string,
  idempotencyKey: string,
  fetcher: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<AdminReactivateResult> {
  validateIdempotencyKey(idempotencyKey);
  return postAdminLifecycle(accountRef, { idempotencyKey }, "reactivate", "reactivate", undefined, fetcher, signal) as Promise<AdminReactivateResult>;
}

export async function continueAdminReactivate(
  accountRef: string,
  fetcher: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<AdminReactivateResult> {
  return postAdminLifecycle(
    accountRef,
    { operation: "reactivate" },
    "lifecycle-recovery",
    "reactivate",
    undefined,
    fetcher,
    signal,
  ) as Promise<AdminReactivateResult>;
}

export async function reassignAdminDepartment(
  accountRef: string,
  idempotencyKey: string,
  departmentId: DepartmentId,
  currentDepartmentId: DepartmentId | null,
  fetcher: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<AdminReassignDepartmentResult> {
  validateIdempotencyKey(idempotencyKey);
  if (!isDepartmentId(departmentId) || (currentDepartmentId !== null && !isDepartmentId(currentDepartmentId)) || departmentId === currentDepartmentId) {
    throw new AdminDirectoryError("validation");
  }
  return postAdminLifecycle(
    accountRef,
    { idempotencyKey, departmentId },
    "reassign-department",
    "reassign_department",
    departmentId,
    fetcher,
    signal,
  ) as Promise<AdminReassignDepartmentResult>;
}

export async function continueAdminDepartmentReassignment(
  accountRef: string,
  departmentId: DepartmentId,
  fetcher: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<AdminReassignDepartmentResult> {
  if (!isDepartmentId(departmentId)) throw new AdminDirectoryError("validation");
  return postAdminLifecycle(
    accountRef,
    { operation: "reassign_department", departmentId },
    "lifecycle-recovery",
    "reassign_department",
    departmentId,
    fetcher,
    signal,
  ) as Promise<AdminReassignDepartmentResult>;
}

export async function loadAdminLifecycleRecoveryStatus(
  accountRef: string,
  fetcher: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<AdminLifecycleRecoveryStatus> {
  if (!accountReferencePattern.test(accountRef)) {
    throw new AdminDirectoryError("validation");
  }
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
    const response = await fetcher(
      `${apiBase}/admin/users/${encodeURIComponent(accountRef)}/lifecycle-recovery-status`,
      {
        method: "GET",
        headers: { Authorization: `Bearer ${token}` },
        signal,
      },
    );
    if (!response.ok) throw new AdminDirectoryError(mapStatus(response.status));
    const parsed = parseAdminLifecycleRecoveryStatus(await response.json());
    if (parsed.accountRef !== accountRef) throw new AdminDirectoryError("validation");
    return parsed;
  } catch (error) {
    if (error instanceof AdminDirectoryError) throw error;
    throw new AdminDirectoryError("unavailable");
  }
}
