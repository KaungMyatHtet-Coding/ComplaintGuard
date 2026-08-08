import type { Locale } from "./i18n";

export type DepartmentMetric = {
  departmentId: string;
  label: string;
  total: number;
  inProgress: number;
  resolved: number;
  avgResolutionHours: number;
};

export type ManagerAnalytics = {
  totalTickets: number;
  activeTickets: number;
  resolvedTickets: number;
  lowConfidenceCount: number;
  avgResolutionHours: number;
  departmentMetrics: DepartmentMetric[];
};

export type LowConfidenceTicket = {
  id: string;
  customerId: string;
  complaintText: string;
  inputLocale: Locale;
  predictedDepartmentId: string | null;
  predictionConfidence: number | null;
  departmentId: string;
  status: string;
  priority: string;
  routingSource: string;
  createdAt: string;
};

export type ManagerOverrideResult = {
  ticketId: string;
  departmentId: string;
  routingSource: "manager_override";
  updatedAt: string;
};

export type ManagerWorkflowErrorCode =
  | "authentication"
  | "permission"
  | "not_found"
  | "validation"
  | "backend";

export class ManagerWorkflowError extends Error {
  constructor(public readonly code: ManagerWorkflowErrorCode) {
    super(code);
  }
}

type Fetcher = typeof fetch;

function getApiUrl(): string {
  const apiUrl = process.env.NEXT_PUBLIC_ML_API_URL || "http://localhost:8000";
  return apiUrl.replace(/\/$/u, "");
}

async function request<T>(
  path: string,
  token: string,
  init: RequestInit = {},
  fetcher: Fetcher = fetch,
): Promise<T> {
  let response: Response;
  try {
    response = await fetcher(`${getApiUrl()}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        ...(init.headers ?? {}),
      },
    });
  } catch {
    throw new ManagerWorkflowError("backend");
  }

  if (response.ok) {
    return (await response.json()) as T;
  }

  if (response.status === 401) {
    throw new ManagerWorkflowError("authentication");
  }
  if (response.status === 403) {
    throw new ManagerWorkflowError("permission");
  }
  if (response.status === 404) {
    throw new ManagerWorkflowError("not_found");
  }
  if (response.status === 400) {
    throw new ManagerWorkflowError("validation");
  }
  throw new ManagerWorkflowError("backend");
}

export async function fetchManagerAnalytics(
  token: string,
  fetcher: Fetcher = fetch,
): Promise<ManagerAnalytics> {
  return request<ManagerAnalytics>("/manager/analytics", token, {}, fetcher);
}

export async function fetchLowConfidenceTickets(
  token: string,
  fetcher: Fetcher = fetch,
): Promise<LowConfidenceTicket[]> {
  return request<LowConfidenceTicket[]>("/manager/low-confidence-tickets", token, {}, fetcher);
}

export async function overrideTicketDepartment(
  token: string,
  ticketId: string,
  newDepartmentId: string,
  reason?: string,
  fetcher: Fetcher = fetch,
  actionId: string = crypto.randomUUID(),
): Promise<ManagerOverrideResult> {
  return request<ManagerOverrideResult>(
    `/manager/tickets/${encodeURIComponent(ticketId)}/override`,
    token,
    {
      method: "POST",
      body: JSON.stringify({
        newDepartmentId,
        reason: reason || null,
        actionId,
      }),
    },
    fetcher,
  );
}
