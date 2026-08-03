import type { Locale } from "./i18n";

export type CustomerTicketSummary = {
  id: string;
  status: string;
  complaintText: string;
  createdAt: string;
  updatedAt: string;
};

export type CustomerMessageItem = {
  messageId: string;
  senderId: string;
  senderRole: "customer" | "staff";
  text: string;
  createdAt: string;
};

export type CustomerTicketDetail = {
  id: string;
  status: string;
  complaintText: string;
  inputLocale: Locale;
  predictedDepartmentId: string | null;
  assignedDepartmentId: string | null;
  priority: string;
  createdAt: string;
  updatedAt: string;
  resolvedAt: string | null;
  messages: CustomerMessageItem[];
  rating?: number;
  feedbackComments?: string;
};

export type CustomerFeedbackResult = {
  ticketId: string;
  rating: number;
  submittedAt: string;
};

export type CustomerWorkflowErrorCode =
  | "authentication"
  | "permission"
  | "not_found"
  | "validation"
  | "backend";

export class CustomerWorkflowError extends Error {
  constructor(public readonly code: CustomerWorkflowErrorCode) {
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
    throw new CustomerWorkflowError("backend");
  }

  if (response.ok) {
    return (await response.json()) as T;
  }

  if (response.status === 401) {
    throw new CustomerWorkflowError("authentication");
  }
  if (response.status === 403) {
    throw new CustomerWorkflowError("permission");
  }
  if (response.status === 404) {
    throw new CustomerWorkflowError("not_found");
  }
  if (response.status === 400) {
    throw new CustomerWorkflowError("validation");
  }
  throw new CustomerWorkflowError("backend");
}

export async function fetchCustomerTickets(
  token: string,
  fetcher: Fetcher = fetch,
): Promise<CustomerTicketSummary[]> {
  return request<CustomerTicketSummary[]>("/customer/tickets", token, {}, fetcher);
}

export async function fetchCustomerTicketDetail(
  token: string,
  ticketId: string,
  fetcher: Fetcher = fetch,
): Promise<CustomerTicketDetail> {
  return request<CustomerTicketDetail>(
    `/customer/tickets/${encodeURIComponent(ticketId)}`,
    token,
    {},
    fetcher,
  );
}

export async function postCustomerMessage(
  token: string,
  ticketId: string,
  text: string,
  fetcher: Fetcher = fetch,
): Promise<CustomerMessageItem> {
  return request<CustomerMessageItem>(
    `/customer/tickets/${encodeURIComponent(ticketId)}/messages`,
    token,
    {
      method: "POST",
      body: JSON.stringify({ text }),
    },
    fetcher,
  );
}

export async function submitCustomerFeedback(
  token: string,
  ticketId: string,
  rating: number,
  comments?: string,
  fetcher: Fetcher = fetch,
): Promise<CustomerFeedbackResult> {
  return request<CustomerFeedbackResult>(
    `/customer/tickets/${encodeURIComponent(ticketId)}/feedback`,
    token,
    {
      method: "POST",
      body: JSON.stringify({ rating, comments }),
    },
    fetcher,
  );
}
