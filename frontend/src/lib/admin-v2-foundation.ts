import { getFirebaseServices } from "./firebase";
import { resolveLocalMlApiBaseUrl } from "./runtime-environment";
import { v2DepartmentIds, type V2DepartmentId } from "./v2-contracts";

export type V2Department = { departmentId: V2DepartmentId; taxonomyVersion: "v2"; nameEn: string; nameMy: string; description: string; state: "active" | "archived"; isCustomerComplaintUnit: boolean; routingEnabled: boolean; assignmentPolicy: { strategy: "priority_then_workload"; languagePreference: boolean; allowManualClaim: boolean }; defaultStaffCapacity: number; serviceIdentityId: string; createdAt: unknown; createdBy: string; updatedAt: unknown; updatedBy: string };
export type V2Staff = { staffId: string; uid: string; employeeCode: string; displayName: string; workEmail: string; departmentIds: V2DepartmentId[]; primaryDepartmentId: V2DepartmentId; position: string; employmentState: string; availabilityState: string; capacity: number; activeWorkload: number; languageSkills: string[]; shift: string; loginEnabled: boolean; joinedAt: unknown; departedAt: unknown; createdAt: unknown; createdBy: string; updatedAt: unknown; updatedBy: string; profileVersion: number; historicalIdentityId: string };
export type V2Page = { departments?: V2Department[]; staff?: V2Staff[]; nextCursor: string | null; hasMore: boolean };

export function isV2DepartmentId(value: unknown): value is V2DepartmentId { return typeof value === "string" && (v2DepartmentIds as readonly string[]).includes(value); }
export function validateFoundationPayload(value: unknown, fields: readonly string[]): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("validation");
  const record = value as Record<string, unknown>;
  if (Object.keys(record).some((key) => !fields.includes(key) || key.includes("_"))) throw new Error("validation");
  return record;
}

async function request<T>(path: string, init: RequestInit = {}, fetcher: typeof fetch = fetch): Promise<T> {
  const { auth } = getFirebaseServices();
  const token = await auth.currentUser?.getIdToken();
  if (!token) throw new Error("authentication");
  const response = await fetcher(`${resolveLocalMlApiBaseUrl()}${path}`, { ...init, headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...(init.headers ?? {}) } });
  if (!response.ok) throw new Error(response.status === 403 ? "permission" : response.status === 422 ? "validation" : response.status === 409 ? "conflict" : "unavailable");
  return (await response.json()) as T;
}

export function listV2Departments(filters: { pageSize?: number; cursor?: string; state?: "active" | "archived" } = {}) { const query = new URLSearchParams(); if (filters.pageSize) query.set("pageSize", String(filters.pageSize)); if (filters.cursor) query.set("cursor", filters.cursor); if (filters.state) query.set("state", filters.state); return request<V2Page>(`/admin/v2/departments?${query}`); }
export function createV2Department(payload: Record<string, unknown>) { validateFoundationPayload(payload, ["departmentId", "nameEn", "nameMy", "description", "isCustomerComplaintUnit", "routingEnabled", "assignmentPolicy", "defaultStaffCapacity", "idempotencyKey"]); return request<V2Department>("/admin/v2/departments", { method: "POST", body: JSON.stringify(payload) }); }
export function updateV2Department(id: string, payload: Record<string, unknown>) { validateFoundationPayload(payload, ["nameEn", "nameMy", "description", "routingEnabled", "assignmentPolicy", "defaultStaffCapacity", "idempotencyKey"]); return request<V2Department>(`/admin/v2/departments/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }); }
export function setV2DepartmentState(id: string, state: "active" | "archived", idempotencyKey: string) { return request<V2Department>(`/admin/v2/departments/${encodeURIComponent(id)}/state?state=${state}&idempotencyKey=${encodeURIComponent(idempotencyKey)}`, { method: "POST" }); }
export function listV2Staff(filters: { pageSize?: number; cursor?: string; employmentState?: string; departmentId?: V2DepartmentId } = {}) { const query = new URLSearchParams(); Object.entries(filters).forEach(([key, value]) => { if (value) query.set(key, String(value)); }); return request<V2Page>(`/admin/v2/staff?${query}`); }
export function createV2Staff(payload: Record<string, unknown>) { validateFoundationPayload(payload, ["employeeCode", "displayName", "workEmail", "departmentIds", "primaryDepartmentId", "position", "employmentState", "availabilityState", "capacity", "languageSkills", "shift", "idempotencyKey"]); return request<V2Staff>("/admin/v2/staff", { method: "POST", body: JSON.stringify(payload) }); }
export function updateV2Staff(id: string, payload: Record<string, unknown>) { validateFoundationPayload(payload, ["displayName", "workEmail", "departmentIds", "primaryDepartmentId", "position", "employmentState", "availabilityState", "capacity", "activeWorkload", "languageSkills", "shift", "loginEnabled", "idempotencyKey"]); return request<V2Staff>(`/admin/v2/staff/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }); }
