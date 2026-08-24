export type CustomerTicketSummary = {
  complaintId: string;
  status: CustomerTicketStatus;
  departmentId: CustomerDepartmentId | null;
  createdAt: string;
  updatedAt: string;
  resolvedAt: string | null;
};

export type CustomerTicketStatus =
  | "submitted"
  | "triaged"
  | "in_progress"
  | "awaiting_customer"
  | "resolved"
  | "closed";

export type CustomerDepartmentId =
  | "transfer_payment"
  | "account_support"
  | "card_atm"
  | "fraud_security"
  | "loan_credit"
  | "general_support";

export type CustomerTicketHistoryPage = {
  tickets: CustomerTicketSummary[];
  nextCursor: string | null;
  hasMore: boolean;
};

export type CustomerMessageItem = {
  senderRole: "customer" | "support_team";
  body: string;
  createdAt: string;
};

export type CustomerTimelineType =
  | "complaint_received"
  | "assigned_to_team"
  | "review_started"
  | "information_requested"
  | "team_replied"
  | "customer_replied"
  | "complaint_resolved"
  | "complaint_closed";

export type CustomerTimelineItem = {
  type: CustomerTimelineType;
  occurredAt: string;
  departmentId?: string | null;
};

export type CustomerTicketDetail = {
  id: string;
  status: string;
  complaintText: string;
  inputLocale: string;
  priority: string;
  departmentId?: string | null;
  createdAt: string;
  updatedAt: string;
  resolvedAt?: string | null;
  messages: CustomerMessageItem[];
  timeline: CustomerTimelineItem[];
  feedback?: {
    rating: number;
    comments?: string;
    submittedAt: string;
  } | null;
};

export type CustomerWorkflowErrorCode =
  | "auth"
  | "permission"
  | "not_found"
  | "conflict"
  | "validation"
  | "backend"
  | "unexpected";

export class CustomerWorkflowError extends Error {
  constructor(public readonly code: CustomerWorkflowErrorCode) {
    super(code);
  }
}

const TICKET_ID_PATTERN = /^ticket_[a-f0-9]{32}$/u;
const CUSTOMER_HISTORY_STATUSES = new Set<CustomerTicketStatus>([
  "submitted",
  "triaged",
  "in_progress",
  "awaiting_customer",
  "resolved",
  "closed",
]);
const CUSTOMER_DEPARTMENTS = new Set<CustomerDepartmentId>([
  "transfer_payment",
  "account_support",
  "card_atm",
  "fraud_security",
  "loan_credit",
  "general_support",
]);
const CURSOR_HASH_PATTERN = /^[0-9a-f]{64}$/u;
const CURSOR_ID_PATTERN = /^ticket_[a-f0-9]{32}$/u;
const CURSOR_MAX_LENGTH = 512;

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) return false;
  const keys = Reflect.ownKeys(value);
  if (keys.some((key) => typeof key !== "string")) return false;
  return keys.every((key) => {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    return Boolean(descriptor?.enumerable && "value" in descriptor);
  });
}

function exactKeys(value: Record<string, unknown>, keys: string[]): boolean {
  const ownKeys = Reflect.ownKeys(value);
  return ownKeys.length === keys.length
    && ownKeys.every((key, index) => key === keys[index]);
}

function parseTimestamp(value: unknown): string | null {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/u.test(value)) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? value : null;
}

function decodeCursorUtf8(value: string): string | null {
  try {
    const padding = "=".repeat((4 - (value.length % 4)) % 4);
    const binary = atob(value.replace(/-/gu, "+").replace(/_/gu, "/") + padding);
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    return null;
  }
}

function encodeCursorUtf8(value: string): string {
  const bytes = new TextEncoder().encode(value);
  let binary = "";
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary).replace(/\+/gu, "-").replace(/\//gu, "_").replace(/=+$/u, "");
}

function validateCursor(value: unknown): string | null {
  if (
    typeof value !== "string"
    || !value
    || value.length > CURSOR_MAX_LENGTH
    || !/^[A-Za-z0-9_-]+$/u.test(value)
    || value.length % 4 === 1
  ) return null;
  const decoded = decodeCursorUtf8(value);
  if (!decoded) return null;
  let payload: unknown;
  try { payload = JSON.parse(decoded) as unknown; } catch { return null; }
  if (!isPlainObject(payload) || !exactKeys(payload, ["v", "customerBinding", "contract", "createdAt", "complaintId"])) return null;
  if (
    payload.v !== 1
    || typeof payload.customerBinding !== "string" || !CURSOR_HASH_PATTERN.test(payload.customerBinding)
    || typeof payload.contract !== "string" || !CURSOR_HASH_PATTERN.test(payload.contract)
    || typeof payload.createdAt !== "string" || !parseTimestamp(payload.createdAt) || !payload.createdAt.endsWith("Z")
    || typeof payload.complaintId !== "string" || !CURSOR_ID_PATTERN.test(payload.complaintId)
  ) return null;
  return encodeCursorUtf8(JSON.stringify(payload)) === value ? value : null;
}

function parseCustomerTicketRow(value: unknown): CustomerTicketSummary {
  if (!isPlainObject(value) || !exactKeys(value, ["complaintId", "status", "departmentId", "createdAt", "updatedAt", "resolvedAt"])) {
    throw new CustomerWorkflowError("unexpected");
  }
  const createdAt = parseTimestamp(value.createdAt);
  const updatedAt = parseTimestamp(value.updatedAt);
  const resolvedAt = value.resolvedAt === null ? null : parseTimestamp(value.resolvedAt);
  if (
    typeof value.complaintId !== "string" || !TICKET_ID_PATTERN.test(value.complaintId)
    || typeof value.status !== "string" || !CUSTOMER_HISTORY_STATUSES.has(value.status as CustomerTicketStatus)
    || (value.departmentId !== null && (typeof value.departmentId !== "string" || !CUSTOMER_DEPARTMENTS.has(value.departmentId as CustomerDepartmentId)))
    || !createdAt || !updatedAt || (value.resolvedAt !== null && !resolvedAt)
  ) throw new CustomerWorkflowError("unexpected");
  if (value.status !== "submitted" && value.departmentId === null) throw new CustomerWorkflowError("unexpected");
  if ((value.status === "resolved" || value.status === "closed") && !resolvedAt) throw new CustomerWorkflowError("unexpected");
  if (value.status !== "resolved" && value.status !== "closed" && resolvedAt) throw new CustomerWorkflowError("unexpected");
  const createdMillis = Date.parse(createdAt);
  const updatedMillis = Date.parse(updatedAt);
  const resolvedMillis = resolvedAt ? Date.parse(resolvedAt) : null;
  if (updatedMillis < createdMillis || (resolvedMillis !== null && resolvedMillis > updatedMillis)) throw new CustomerWorkflowError("unexpected");
  return {
    complaintId: value.complaintId,
    status: value.status as CustomerTicketStatus,
    departmentId: value.departmentId as CustomerDepartmentId | null,
    createdAt,
    updatedAt,
    resolvedAt,
  };
}

export function parseCustomerTicketHistoryPage(value: unknown): CustomerTicketHistoryPage {
  if (!isPlainObject(value) || !exactKeys(value, ["tickets", "nextCursor", "hasMore"]) || !Array.isArray(value.tickets) || typeof value.hasMore !== "boolean") {
    throw new CustomerWorkflowError("unexpected");
  }
  if (value.nextCursor !== null && validateCursor(value.nextCursor) === null) throw new CustomerWorkflowError("unexpected");
  if (value.hasMore !== (value.nextCursor !== null)) throw new CustomerWorkflowError("unexpected");
  const tickets = value.tickets.map(parseCustomerTicketRow);
  const ids = tickets.map((ticket) => ticket.complaintId);
  if (new Set(ids).size !== ids.length) throw new CustomerWorkflowError("unexpected");
  return { tickets, nextCursor: value.nextCursor as string | null, hasMore: value.hasMore };
}

import { resolveLocalMlApiBaseUrl } from "./runtime-environment";

type Fetcher = typeof fetch;

function getApiUrl(): string {
  try {
    return resolveLocalMlApiBaseUrl();
  } catch {
    throw new CustomerWorkflowError("backend");
  }
}

export async function fetchCustomerTickets(
  idToken: string,
  options: { pageSize?: number; cursor?: string | null; signal?: AbortSignal; fetcher?: Fetcher } = {},
): Promise<CustomerTicketHistoryPage> {
  const pageSize = options.pageSize ?? 25;
  if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > 50) throw new CustomerWorkflowError("validation");
  if (options.cursor !== undefined && options.cursor !== null && validateCursor(options.cursor) === null) throw new CustomerWorkflowError("validation");
  const baseUrl = getApiUrl();
  const params = new URLSearchParams({ pageSize: String(pageSize) });
  if (options.cursor) params.set("cursor", options.cursor);
  let response: Response;
  try {
    response = await (options.fetcher ?? fetch)(`${baseUrl}/customer/tickets?${params.toString()}`, {
      headers: { Authorization: `Bearer ${idToken}` },
      signal: options.signal,
    });
  } catch {
    throw new CustomerWorkflowError("backend");
  }

  if (response.status === 401) throw new CustomerWorkflowError("auth");
  if (response.status === 403) throw new CustomerWorkflowError("permission");
  if (response.status === 422) throw new CustomerWorkflowError("validation");
  if (!response.ok) throw new CustomerWorkflowError("backend");
  try { return parseCustomerTicketHistoryPage(await response.json() as unknown); }
  catch (error) { if (error instanceof CustomerWorkflowError) throw error; throw new CustomerWorkflowError("unexpected"); }
}

export async function fetchCustomerTicketDetail(
  ticketId: string,
  idToken: string,
  fetcher: Fetcher = fetch,
  signal?: AbortSignal,
): Promise<CustomerTicketDetail> {
  const baseUrl = getApiUrl();
  let response: Response;
  try {
    response = await fetcher(`${baseUrl}/customer/tickets/${encodeURIComponent(ticketId)}`, {
      headers: { Authorization: `Bearer ${idToken}` },
      signal,
    });
  } catch {
    throw new CustomerWorkflowError("backend");
  }

  if (response.status === 401) throw new CustomerWorkflowError("auth");
  if (response.status === 403) throw new CustomerWorkflowError("permission");
  if (response.status === 404) throw new CustomerWorkflowError("not_found");
  if (!response.ok) throw new CustomerWorkflowError("backend");

  const data: unknown = await response.json();
  if (!data || typeof data !== "object" || typeof (data as { id?: unknown }).id !== "string") {
    throw new CustomerWorkflowError("unexpected");
  }

  return data as CustomerTicketDetail;
}

export async function sendCustomerMessage(
  ticketId: string,
  messageText: string,
  idToken: string,
  fetcher: Fetcher = fetch,
  actionId: string = crypto.randomUUID()
): Promise<CustomerMessageItem> {
  const baseUrl = getApiUrl();
  let response: Response;
  try {
    response = await fetcher(`${baseUrl}/customer/tickets/${ticketId}/messages`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${idToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ messageText, actionId }),
    });
  } catch {
    throw new CustomerWorkflowError("backend");
  }

  if (response.status === 401) throw new CustomerWorkflowError("auth");
  if (response.status === 403) throw new CustomerWorkflowError("permission");
  if (response.status === 404) throw new CustomerWorkflowError("not_found");
  if (response.status === 409) throw new CustomerWorkflowError("conflict");
  if (response.status === 422) throw new CustomerWorkflowError("validation");
  if (!response.ok) throw new CustomerWorkflowError("backend");

  const data: unknown = await response.json();
  if (!data || typeof data !== "object" || typeof (data as { body?: unknown }).body !== "string") {
    throw new CustomerWorkflowError("unexpected");
  }

  return data as CustomerMessageItem;
}

export async function submitCustomerFeedback(
  ticketId: string,
  rating: number,
  comments: string,
  idToken: string,
  fetcher: Fetcher = fetch,
  actionId: string = crypto.randomUUID()
): Promise<{ ticketId: string; feedbackId: string; status: string }> {
  const baseUrl = getApiUrl();
  let response: Response;
  try {
    response = await fetcher(`${baseUrl}/customer/tickets/${ticketId}/feedback`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${idToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ rating, comments, actionId }),
    });
  } catch {
    throw new CustomerWorkflowError("backend");
  }

  if (response.status === 401) throw new CustomerWorkflowError("auth");
  if (response.status === 403) throw new CustomerWorkflowError("permission");
  if (response.status === 404) throw new CustomerWorkflowError("not_found");
  if (response.status === 409) throw new CustomerWorkflowError("conflict");
  if (response.status === 422) throw new CustomerWorkflowError("validation");
  if (!response.ok) throw new CustomerWorkflowError("backend");

  const data: unknown = await response.json();
  if (!data || typeof data !== "object" || typeof (data as { feedbackId?: unknown }).feedbackId !== "string") {
    throw new CustomerWorkflowError("unexpected");
  }

  return data as { ticketId: string; feedbackId: string; status: string };
}
