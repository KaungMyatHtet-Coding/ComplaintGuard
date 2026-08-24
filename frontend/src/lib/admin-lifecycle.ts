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

export type AdminLifecycleRequestOutcome = "definitive" | "unknown";

export class AdminLifecycleRequestError extends AdminDirectoryError {
  constructor(
    code: AdminDirectoryErrorCode,
    public readonly outcome: AdminLifecycleRequestOutcome,
    public readonly httpStatus?: number,
  ) {
    super(code);
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
  endpoint: "disable" | "lifecycle-recovery",
  fetcher: typeof fetch,
  signal: AbortSignal | undefined,
): Promise<AdminDisableResult> {
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
    throw new AdminLifecycleRequestError(mapStatus(response.status), "definitive", response.status);
  }
  try {
    const parsed = parseAdminDisableResult(await response.json());
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
  return postAdminLifecycle(accountRef, { idempotencyKey }, "disable", fetcher, signal);
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
    fetcher,
    signal,
  );
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
