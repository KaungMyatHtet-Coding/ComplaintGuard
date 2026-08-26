import { getFirebaseServices } from "./firebase";
import { resolveLocalMlApiBaseUrl } from "./runtime-environment";
import { isDepartmentId, type DepartmentId } from "./department-labels";
import type { Locale } from "./i18n";

export type AdminProvisioningRole = "staff" | "manager";

export type AdminProvisioningFormInput = {
  email: string;
  displayName: string;
  locale: Locale;
  role: AdminProvisioningRole;
  departmentId: DepartmentId | null;
};

export type AdminProvisioningRequest = AdminProvisioningFormInput & {
  idempotencyKey: string;
};

export type AdminProvisioningResponse = {
  status: "pending_setup";
  uid?: string | null;
  email: string;
  displayName: string;
  locale: Locale;
  role: AdminProvisioningRole;
  departmentId: DepartmentId | null;
  active: false;
  setupRequired: true;
};

export type AdminProvisioningErrorCode =
  | "authentication"
  | "permission"
  | "email_exists"
  | "profile_conflict"
  | "idempotency_conflict"
  | "provisioning_incomplete"
  | "validation"
  | "unavailable"
  | "unexpected";

export class AdminProvisioningError extends Error {
  constructor(public readonly code: AdminProvisioningErrorCode) {
    super(code);
  }
}

export function validateAdminProvisioningForm(
  value: unknown,
): AdminProvisioningFormInput {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new AdminProvisioningError("validation");
  }
  const record = value as Record<string, unknown>;
  const allowedFields = new Set([
    "email",
    "displayName",
    "locale",
    "role",
    "departmentId",
    "idempotencyKey",
  ]);
  if (Object.keys(record).some((key) => !allowedFields.has(key))) {
    throw new AdminProvisioningError("validation");
  }
  const email = typeof record.email === "string" ? record.email.trim().toLowerCase() : "";
  const displayName =
    typeof record.displayName === "string"
      ? record.displayName.trim().replace(/\s+/gu, " ")
      : "";
  const role = record.role;
  const locale = record.locale;
  const departmentId = record.departmentId;

  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/u.test(email)) {
    throw new AdminProvisioningError("validation");
  }
  if (!displayName || displayName.length > 100) {
    throw new AdminProvisioningError("validation");
  }
  if (locale !== "en" && locale !== "my") {
    throw new AdminProvisioningError("validation");
  }
  if (role !== "staff" && role !== "manager") {
    throw new AdminProvisioningError("validation");
  }
  if (role === "staff" && !isDepartmentId(departmentId as string | null)) {
    throw new AdminProvisioningError("validation");
  }
  if (role === "manager" && departmentId !== null) {
    throw new AdminProvisioningError("validation");
  }

  return {
    email,
    displayName,
    locale,
    role,
    departmentId: role === "staff" ? (departmentId as DepartmentId) : null,
  };
}

export function createIdempotencyKey(): string {
  const randomUuid = globalThis.crypto?.randomUUID;
  if (typeof randomUuid !== "function") {
    throw new AdminProvisioningError("unavailable");
  }
  return randomUuid.call(globalThis.crypto);
}

function safeBackendCode(value: unknown): AdminProvisioningErrorCode | null {
  if (typeof value !== "string") return null;
  const allowed: AdminProvisioningErrorCode[] = [
    "authentication",
    "permission",
    "email_exists",
    "profile_conflict",
    "idempotency_conflict",
    "provisioning_incomplete",
    "validation",
    "unavailable",
    "unexpected",
  ];
  return allowed.includes(value as AdminProvisioningErrorCode)
    ? (value as AdminProvisioningErrorCode)
    : null;
}

async function responseCode(response: Response): Promise<AdminProvisioningErrorCode | null> {
  try {
    const body = (await response.clone().json()) as { code?: unknown; detail?: { code?: unknown } };
    return safeBackendCode(body.code) ?? safeBackendCode(body.detail?.code);
  } catch {
    return null;
  }
}

function mapResponseError(status: number, code: AdminProvisioningErrorCode | null): AdminProvisioningError {
  if (status === 401) return new AdminProvisioningError("authentication");
  if (status === 403) return new AdminProvisioningError("permission");
  if (status === 422) return new AdminProvisioningError("validation");
  if (status === 409) {
    if (code === "email_exists" || code === "profile_conflict" || code === "idempotency_conflict") {
      return new AdminProvisioningError(code);
    }
    return new AdminProvisioningError("profile_conflict");
  }
  if (status === 503) {
    return new AdminProvisioningError(
      code === "provisioning_incomplete" ? "provisioning_incomplete" : "unavailable",
    );
  }
  return new AdminProvisioningError("unexpected");
}

export async function provisionAdminUser(
  value: unknown,
  fetcher: typeof fetch = fetch,
): Promise<AdminProvisioningResponse> {
  let apiBase: string;
  let input: AdminProvisioningFormInput;
  try {
    apiBase = resolveLocalMlApiBaseUrl();
    input = validateAdminProvisioningForm(value);
  } catch (error) {
    if (error instanceof AdminProvisioningError) throw error;
    throw new AdminProvisioningError("unavailable");
  }
  const record = value as Record<string, unknown>;
  const idempotencyKey = typeof record.idempotencyKey === "string" ? record.idempotencyKey : "";
  if (!/^[A-Za-z0-9_-]{8,64}$/u.test(idempotencyKey)) {
    throw new AdminProvisioningError("validation");
  }

  let auth;
  try {
    auth = getFirebaseServices().auth;
  } catch {
    throw new AdminProvisioningError("unavailable");
  }
  const user = auth.currentUser;
  if (!user) throw new AdminProvisioningError("authentication");

  let token: string;
  try {
    token = await user.getIdToken(true);
  } catch {
    throw new AdminProvisioningError("authentication");
  }
  if (!token) throw new AdminProvisioningError("authentication");

  const payload = {
    email: input.email,
    displayName: input.displayName,
    locale: input.locale,
    role: input.role,
    ...(input.role === "staff" ? { departmentId: input.departmentId } : {}),
    idempotencyKey,
  };
  let response: Response;
  try {
    response = await fetcher(`${apiBase}/admin/users`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new AdminProvisioningError("unavailable");
  }
  if (!response.ok) throw mapResponseError(response.status, await responseCode(response));
  try {
    return (await response.json()) as AdminProvisioningResponse;
  } catch {
    throw new AdminProvisioningError("unexpected");
  }
}
