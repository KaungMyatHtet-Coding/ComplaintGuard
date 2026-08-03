import type { Locale } from "./i18n";

export type StaffTicketStatus =
  | "triaged"
  | "in_progress"
  | "awaiting_customer"
  | "resolved";
export type StaffPriority = "normal" | "high" | "urgent";

export type StaffTicket = {
  ticketId: string;
  customerId: string;
  complaintText: string;
  inputLocale: Locale;
  departmentId: string;
  status: StaffTicketStatus;
  priority: StaffPriority;
  assignedStaffId: string | null;
  predictedDepartmentId: string | null;
  predictionConfidence: number | null;
  routingSource: "model" | "manual_review" | "manager_override";
  escalated: boolean;
  resolutionSummary: string | null;
  createdAt: string;
  updatedAt: string;
  resolvedAt: string | null;
};

export type StaffMessage = {
  messageId: string;
  authorId: string;
  authorRole: "customer" | "staff" | "manager";
  body: string;
  visibility: "participants";
  createdAt: string;
};

export type StaffEvent = {
  eventId: string;
  type: string;
  actorId: string;
  actorRole: "staff" | "manager" | "system";
  fromValue: string | null;
  toValue: string | null;
  createdAt: string;
};

export type StaffTicketDetail = StaffTicket & {
  messages: StaffMessage[];
  events: StaffEvent[];
};

export type StaffFilters = {
  status?: StaffTicketStatus;
  priority?: StaffPriority;
  createdFrom?: string;
  createdTo?: string;
};

export type StaffWorkflowErrorCode =
  | "authentication"
  | "permission"
  | "not_found"
  | "validation"
  | "conflict"
  | "backend";

export class StaffWorkflowError extends Error {
  constructor(public readonly code: StaffWorkflowErrorCode) {
    super(code);
  }
}

type Fetcher = typeof fetch;

function apiBase(): string {
  const value = process.env.NEXT_PUBLIC_ML_API_URL || "http://localhost:8000";
  return value.replace(/\/$/u, "");
}

async function request<T>(
  path: string,
  token: string,
  init: RequestInit = {},
  fetcher: Fetcher = fetch,
): Promise<T> {
  let response: Response;
  try {
    response = await fetcher(`${apiBase()}${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(init.body ? { "Content-Type": "application/json" } : {}),
      },
    });
  } catch {
    throw new StaffWorkflowError("backend");
  }
  if (response.status === 401) throw new StaffWorkflowError("authentication");
  if (response.status === 403) throw new StaffWorkflowError("permission");
  if (response.status === 404) throw new StaffWorkflowError("not_found");
  if (response.status === 409) throw new StaffWorkflowError("conflict");
  if (response.status === 422) throw new StaffWorkflowError("validation");
  if (!response.ok) throw new StaffWorkflowError("backend");
  return (await response.json()) as T;
}

export async function loadStaffTickets(
  token: string,
  filters: StaffFilters,
  fetcher: Fetcher = fetch,
): Promise<StaffTicket[]> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.priority) params.set("priority", filters.priority);
  if (filters.createdFrom) params.set("created_from", filters.createdFrom);
  if (filters.createdTo) params.set("created_to", filters.createdTo);
  const query = params.size ? `?${params.toString()}` : "";
  const response = await request<{ tickets: StaffTicket[] }>(
    `/staff/tickets${query}`,
    token,
    {},
    fetcher,
  );
  return response.tickets;
}

export function loadStaffTicket(
  token: string,
  ticketId: string,
  fetcher: Fetcher = fetch,
): Promise<StaffTicketDetail> {
  return request(`/staff/tickets/${encodeURIComponent(ticketId)}`, token, {}, fetcher);
}

export function replyToTicket(
  token: string,
  ticketId: string,
  body: string,
  actionId: string,
  fetcher: Fetcher = fetch,
) {
  return request(`/staff/tickets/${encodeURIComponent(ticketId)}/replies`, token, {
    method: "POST",
    body: JSON.stringify({ body, actionId }),
  }, fetcher);
}

export function transitionTicket(
  token: string,
  ticketId: string,
  status: "in_progress" | "awaiting_customer" | "resolved",
  actionId: string,
  resolutionSummary?: string,
  fetcher: Fetcher = fetch,
) {
  return request(`/staff/tickets/${encodeURIComponent(ticketId)}/transitions`, token, {
    method: "POST",
    body: JSON.stringify({ status, actionId, ...(resolutionSummary ? { resolutionSummary } : {}) }),
  }, fetcher);
}

export function requestStaffAction(
  token: string,
  ticketId: string,
  type: "request_reassignment" | "request_escalation",
  reason: string,
  actionId: string,
  fetcher: Fetcher = fetch,
) {
  return request(`/staff/tickets/${encodeURIComponent(ticketId)}/requests`, token, {
    method: "POST",
    body: JSON.stringify({ type, reason, actionId }),
  }, fetcher);
}
