import { getFirebaseServices } from "./firebase";
import { resolveLocalMlApiBaseUrl } from "./runtime-environment";

export const NOTIFICATION_PAGE_SIZE = 50;

export const notificationTypes = [
  "complaint_received",
  "department_assigned",
  "staff_reply",
  "information_requested",
  "status_changed",
  "complaint_resolved",
  "response_target_approaching",
  "response_target_overdue",
  "department_complaint_available",
  "ticket_assigned",
  "customer_reply",
  "high_priority_ticket",
  "manager_reassigned",
  "escalation_updated",
  "manual_review_required",
  "unassigned_ticket",
  "overdue_ticket",
  "escalation_requested",
  "workload_imbalance_observed",
  "pending_account_setup",
  "account_operation_issue",
  "department_workload_observation",
  "system_operational_alert",
] as const;

export type NotificationType = (typeof notificationTypes)[number];
export type NotificationSeverity = "info" | "attention" | "urgent";
export type NotificationCategory =
  | "complaint"
  | "assignment"
  | "response"
  | "sla"
  | "account"
  | "workload"
  | "system";
export type NotificationNavigationTarget =
  | "notifications"
  | "customer_ticket"
  | "staff_queue"
  | "staff_ticket"
  | "manager_operations"
  | "manager_manual_review"
  | "admin_accounts"
  | "admin_overview";

export type NotificationParamValue = string | number | boolean;
export type NotificationParams = Record<string, NotificationParamValue>;

export type NotificationItem = {
  notificationRef: string;
  type: NotificationType;
  severity: NotificationSeverity;
  category: NotificationCategory;
  relatedTicketRef: string | null;
  titleKey: string;
  bodyKey: string;
  params: NotificationParams;
  navigationTarget: NotificationNavigationTarget;
  createdAt: string;
  readAt: string | null;
  unread: boolean;
};

export type NotificationListResponse = {
  notifications: NotificationItem[];
  nextCursor: string | null;
};

export type NotificationUnreadCountResponse = { unreadCount: number };
export type NotificationReadAllResponse = { updatedCount: number };

export type NotificationErrorCode =
  | "auth"
  | "permission"
  | "validation"
  | "unavailable"
  | "unexpected"
  | "aborted";

export class NotificationError extends Error {
  constructor(public readonly code: NotificationErrorCode) {
    super(code);
  }
}

const typeSet = new Set<string>(notificationTypes);
const severitySet = new Set<NotificationSeverity>(["info", "attention", "urgent"]);
const categorySet = new Set<NotificationCategory>([
  "complaint",
  "assignment",
  "response",
  "sla",
  "account",
  "workload",
  "system",
]);
const targetSet = new Set<NotificationNavigationTarget>([
  "notifications",
  "customer_ticket",
  "staff_queue",
  "staff_ticket",
  "manager_operations",
  "manager_manual_review",
  "admin_accounts",
  "admin_overview",
]);
const safeRefPattern = /^[A-Za-z0-9_-]{1,128}$/;
const notificationRefPattern = /^[0-9a-f]{64}$/;
const safeParamKeys: Record<NotificationType, readonly string[]> = {
  complaint_received: ["ticketRef"],
  department_assigned: ["ticketRef", "departmentKey"],
  staff_reply: ["ticketRef"],
  information_requested: ["ticketRef"],
  status_changed: ["ticketRef", "status"],
  complaint_resolved: ["ticketRef"],
  response_target_approaching: ["ticketRef"],
  response_target_overdue: ["ticketRef"],
  department_complaint_available: ["ticketRef", "departmentKey"],
  ticket_assigned: ["ticketRef"],
  customer_reply: ["ticketRef"],
  high_priority_ticket: ["ticketRef", "priority"],
  manager_reassigned: ["ticketRef", "departmentKey"],
  escalation_updated: ["ticketRef", "status"],
  manual_review_required: ["ticketRef"],
  unassigned_ticket: ["ticketRef"],
  overdue_ticket: ["ticketRef"],
  escalation_requested: ["ticketRef"],
  workload_imbalance_observed: ["departmentKey"],
  pending_account_setup: [],
  account_operation_issue: [],
  department_workload_observation: ["departmentKey"],
  system_operational_alert: [],
};

function getApiBase(): string {
  try {
    return resolveLocalMlApiBaseUrl();
  } catch {
    throw new NotificationError("unavailable");
  }
}

function mapStatus(status: number): NotificationErrorCode {
  if (status === 401) return "auth";
  if (status === 403) return "permission";
  if (status === 422) return "validation";
  if (status === 503) return "unavailable";
  return "unexpected";
}

async function getFreshToken(): Promise<string> {
  let user: { getIdToken: (forceRefresh?: boolean) => Promise<string> } | null;
  try {
    user = getFirebaseServices().auth.currentUser;
  } catch {
    throw new NotificationError("unavailable");
  }
  if (!user) throw new NotificationError("auth");
  try {
    const token = await user.getIdToken(true);
    if (!token) throw new Error("empty token");
    return token;
  } catch {
    throw new NotificationError("auth");
  }
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
  fetcher: typeof fetch = fetch,
): Promise<T> {
  const token = await getFreshToken();
  let response: Response;
  try {
    response = await fetcher(`${getApiBase()}${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(init.headers ?? {}),
      },
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new NotificationError("aborted");
    }
    throw new NotificationError("unavailable");
  }
  if (!response.ok) throw new NotificationError(mapStatus(response.status));
  try {
    return (await response.json()) as T;
  } catch {
    throw new NotificationError("unexpected");
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}

function isValidDateString(value: unknown): value is string {
  return isString(value) && !Number.isNaN(Date.parse(value));
}

function isNotificationType(value: unknown): value is NotificationType {
  return isString(value) && typeSet.has(value);
}

function isSafeParams(type: NotificationType, value: unknown): value is NotificationParams {
  if (!isRecord(value) || Object.keys(value).length > 4) return false;
  const allowed = new Set(safeParamKeys[type]);
  return Object.entries(value).every(([key, item]) => {
    if (!allowed.has(key)) return false;
    if (typeof item === "string") return item.length > 0 && item.length <= 120 && !/[\r\n]/.test(item);
    return typeof item === "number" || typeof item === "boolean";
  });
}

function isSafeLocalizationKey(value: unknown, type: NotificationType, suffix: "title" | "body"): value is string {
  return value === `notifications.${type}.${suffix}`;
}

export function parseNotificationItem(value: unknown): NotificationItem {
  if (!isRecord(value)) throw new NotificationError("unexpected");
  const allowedFields = new Set([
    "notificationRef", "type", "severity", "category", "relatedTicketRef",
    "titleKey", "bodyKey", "params", "navigationTarget", "createdAt", "readAt", "unread",
  ]);
  if (Object.keys(value).some((key) => !allowedFields.has(key))) throw new NotificationError("unexpected");
  const type = value.type;
  if (
    !isString(value.notificationRef) || !notificationRefPattern.test(value.notificationRef) ||
    !isNotificationType(type) || !isString(value.severity) || !severitySet.has(value.severity as NotificationSeverity) ||
    !isString(value.category) || !categorySet.has(value.category as NotificationCategory) ||
    (value.relatedTicketRef !== null && (!isString(value.relatedTicketRef) || !safeRefPattern.test(value.relatedTicketRef))) ||
    !isSafeLocalizationKey(value.titleKey, type, "title") || !isSafeLocalizationKey(value.bodyKey, type, "body") ||
    !isSafeParams(type, value.params) || !isString(value.navigationTarget) || !targetSet.has(value.navigationTarget as NotificationNavigationTarget) ||
    !isValidDateString(value.createdAt) || (value.readAt !== null && !isValidDateString(value.readAt)) || typeof value.unread !== "boolean"
  ) {
    throw new NotificationError("unexpected");
  }
  return {
    notificationRef: value.notificationRef,
    type,
    severity: value.severity as NotificationSeverity,
    category: value.category as NotificationCategory,
    relatedTicketRef: value.relatedTicketRef as string | null,
    titleKey: value.titleKey,
    bodyKey: value.bodyKey,
    params: value.params,
    navigationTarget: value.navigationTarget as NotificationNavigationTarget,
    createdAt: value.createdAt,
    readAt: value.readAt as string | null,
    unread: value.unread,
  };
}

export function parseNotificationList(value: unknown): NotificationListResponse {
  if (!isRecord(value) || Object.keys(value).some((key) => !new Set(["notifications", "nextCursor"]).has(key)) || !Array.isArray(value.notifications) || (value.nextCursor !== null && (!isString(value.nextCursor) || value.nextCursor.length > 512))) {
    throw new NotificationError("unexpected");
  }
  return {
    notifications: value.notifications.map(parseNotificationItem),
    nextCursor: value.nextCursor as string | null,
  };
}

export function formatNotificationCount(value: number): string {
  return value > 99 ? "99+" : String(Math.max(0, value));
}

export async function listNotifications(
  options: { unreadOnly?: boolean; cursor?: string | null; fetcher?: typeof fetch; signal?: AbortSignal } = {},
): Promise<NotificationListResponse> {
  const params = new URLSearchParams({ pageSize: String(NOTIFICATION_PAGE_SIZE) });
  if (options.unreadOnly) params.set("unreadOnly", "true");
  if (options.cursor) params.set("cursor", options.cursor);
  const response = await requestJson<unknown>(`/notifications?${params.toString()}`, { signal: options.signal }, options.fetcher);
  return parseNotificationList(response);
}

export async function getUnreadNotificationCount(fetcher: typeof fetch = fetch, signal?: AbortSignal): Promise<number> {
  const response = await requestJson<unknown>("/notifications/unread-count", { signal }, fetcher);
  const count = isRecord(response) ? response.unreadCount : undefined;
  if (!isRecord(response) || Object.keys(response).some((key) => key !== "unreadCount") || !Number.isInteger(count) || (count as number) < 0) {
    throw new NotificationError("unexpected");
  }
  return count as number;
}

export async function markNotificationRead(notificationRef: string, fetcher: typeof fetch = fetch, signal?: AbortSignal): Promise<string> {
  if (!notificationRefPattern.test(notificationRef)) throw new NotificationError("validation");
  const response = await requestJson<unknown>(`/notifications/${encodeURIComponent(notificationRef)}/read`, { method: "POST", signal }, fetcher);
  if (!isRecord(response) || Object.keys(response).some((key) => !new Set(["notificationRef", "readAt"]).has(key)) || response.notificationRef !== notificationRef || !isString(response.readAt)) {
    throw new NotificationError("unexpected");
  }
  return response.readAt;
}

export async function markAllNotificationsRead(fetcher: typeof fetch = fetch, signal?: AbortSignal): Promise<number> {
  const response = await requestJson<unknown>("/notifications/read-all", { method: "POST", signal }, fetcher);
  const count = isRecord(response) ? response.updatedCount : undefined;
  if (!isRecord(response) || Object.keys(response).some((key) => key !== "updatedCount") || !Number.isInteger(count) || (count as number) < 0) {
    throw new NotificationError("unexpected");
  }
  return count as number;
}

export function getSafeNotificationTarget(notification: NotificationItem): string | null {
  if (notification.navigationTarget !== "customer_ticket" || !notification.relatedTicketRef || !safeRefPattern.test(notification.relatedTicketRef)) {
    return null;
  }
  return `/dashboard?ticketRef=${encodeURIComponent(notification.relatedTicketRef)}`;
}
