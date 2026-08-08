export type CustomerTicketSummary = {
  id: string;
  status: string;
  predictedDepartmentId?: string | null;
  predictionConfidence?: number | null;
  routingSource?: "model" | "manual_review" | "manager_override" | "pending";
  assignedDepartmentId?: string | null;
  createdAt: string;
  updatedAt: string;
  summaryText: string;
};

export type CustomerMessageItem = {
  id: string;
  senderId: string;
  senderRole: "customer" | "staff" | "manager" | "system";
  text: string;
  createdAt: string;
};

export type CustomerTicketDetail = {
  id: string;
  customerId: string;
  status: string;
  complaintText: string;
  inputLocale: string;
  predictedDepartmentId?: string | null;
  predictionConfidence?: number | null;
  routingSource?: "model" | "manual_review" | "manager_override" | "pending";
  assignedDepartmentId?: string | null;
  priority: string;
  createdAt: string;
  updatedAt: string;
  resolvedAt?: string | null;
  messages: CustomerMessageItem[];
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

type Fetcher = typeof fetch;

function getApiUrl(): string {
  const apiUrl = process.env.NEXT_PUBLIC_ML_API_URL || "http://localhost:8000";
  return apiUrl.replace(/\/$/u, "");
}

export async function fetchCustomerTickets(
  idToken: string,
  fetcher: Fetcher = fetch
): Promise<CustomerTicketSummary[]> {
  const baseUrl = getApiUrl();
  let response: Response;
  try {
    response = await fetcher(`${baseUrl}/customer/tickets`, {
      headers: { Authorization: `Bearer ${idToken}` },
    });
  } catch {
    throw new CustomerWorkflowError("backend");
  }

  if (response.status === 401) throw new CustomerWorkflowError("auth");
  if (response.status === 403) throw new CustomerWorkflowError("permission");
  if (!response.ok) throw new CustomerWorkflowError("backend");

  const data: unknown = await response.json();
  if (!data || typeof data !== "object" || !Array.isArray((data as { tickets?: unknown }).tickets)) {
    throw new CustomerWorkflowError("unexpected");
  }

  return (data as { tickets: CustomerTicketSummary[] }).tickets;
}

export async function fetchCustomerTicketDetail(
  ticketId: string,
  idToken: string,
  fetcher: Fetcher = fetch
): Promise<CustomerTicketDetail> {
  const baseUrl = getApiUrl();
  let response: Response;
  try {
    response = await fetcher(`${baseUrl}/customer/tickets/${ticketId}`, {
      headers: { Authorization: `Bearer ${idToken}` },
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
  if (!data || typeof data !== "object" || typeof (data as { text?: unknown }).text !== "string") {
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
