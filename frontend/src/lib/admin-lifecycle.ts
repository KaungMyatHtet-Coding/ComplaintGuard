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

function mapStatus(status: number): AdminDirectoryErrorCode {
  if (status === 401) return "authentication";
  if (status === 403) return "permission";
  if (status === 404) return "notFound";
  if (status === 422) return "validation";
  if (status === 503) return "unavailable";
  return "unexpected";
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
