import type { Locale } from "@/lib/i18n";

export const v2DepartmentIds = [
  "account_branch_services",
  "cards_atm_pos",
  "mobile_internet_banking",
  "transfers_payments_remittance",
  "loans_credit",
  "fraud_scam_unauthorized",
  "kyc_verification_restrictions",
  "general_complaints",
] as const;

export type V2DepartmentId = (typeof v2DepartmentIds)[number];

export const v2LifecycleStatuses = [
  "received",
  "queued",
  "assigned",
  "under_investigation",
  "additional_information_required",
  "action_in_progress",
  "resolved",
  "closed",
  "reopened",
] as const;

export type V2LifecycleStatus = (typeof v2LifecycleStatuses)[number];

export const staffEmploymentStates = [
  "invited",
  "active",
  "on_leave",
  "suspended",
  "departed",
  "archived",
] as const;

export type StaffEmploymentState = (typeof staffEmploymentStates)[number];

export const staffAvailabilityStates = ["available", "busy", "offline", "unavailable"] as const;

export type StaffAvailabilityState = (typeof staffAvailabilityStates)[number];

export type TicketVersion = "v1" | "v2";

export type V2TicketContract = {
  schemaVersion: "v2";
  workflowVersion: "v2";
  taxonomyVersion: "v2";
  categoryId: V2DepartmentId;
  status: V2LifecycleStatus;
};

const v1Statuses = ["submitted", "triaged", "in_progress", "awaiting_customer", "resolved", "closed"] as const;
const v1DepartmentIds = ["transfer_payment", "account_support", "card_atm", "fraud_security", "loan_credit", "general_support"] as const;

export const v2DepartmentLabels: Record<V2DepartmentId, Record<Locale, string>> = {
  account_branch_services: { en: "Account & Branch Services", my: "အကောင့်နှင့် ဘဏ်ခွဲဝန်ဆောင်မှု" },
  cards_atm_pos: { en: "Cards, ATM & POS", my: "ကတ်၊ ATM နှင့် POS" },
  mobile_internet_banking: { en: "Mobile & Internet Banking", my: "မိုဘိုင်းနှင့် အင်တာနက်ဘဏ်လုပ်ငန်း" },
  transfers_payments_remittance: { en: "Transfers, Payments & Remittance", my: "ငွေလွှဲ၊ ပေးချေမှုနှင့် ငွေလွှဲပို့မှု" },
  loans_credit: { en: "Loans & Credit", my: "ချေးငွေနှင့် အကြွေး" },
  fraud_scam_unauthorized: { en: "Fraud, Scam & Unauthorized Transactions", my: "လိမ်လည်မှု၊ လှည့်ဖြားမှုနှင့် ခွင့်မပြုသော ငွေလွှဲမှု" },
  kyc_verification_restrictions: { en: "KYC, Verification & Account Restrictions", my: "KYC၊ အတည်ပြုခြင်းနှင့် အကောင့်ကန့်သတ်ချက်များ" },
  general_complaints: { en: "Customer Complaint Unit", my: "ဖောက်သည်တိုင်ကြားချက်များဌာန" },
};

export const v2LifecycleLabels: Record<V2LifecycleStatus, Record<Locale, string>> = {
  received: { en: "Received", my: "လက်ခံရရှိပြီး" },
  queued: { en: "In queue", my: "တန်းစီနေသည်" },
  assigned: { en: "Assigned to support", my: "အကူအညီပေးသူထံ ခန့်အပ်ထားသည်" },
  under_investigation: { en: "Under investigation", my: "စိစစ်နေသည်" },
  additional_information_required: { en: "More information needed", my: "အချက်အလက် ထပ်မံလိုအပ်သည်" },
  action_in_progress: { en: "Action in progress", my: "ဆောင်ရွက်နေသည်" },
  resolved: { en: "Resolution provided", my: "ဖြေရှင်းချက် ပေးပြီး" },
  closed: { en: "Closed", my: "ပိတ်သိမ်းပြီး" },
  reopened: { en: "Reopened", my: "ပြန်လည်ဖွင့်ထားသည်" },
};

export const staffEmploymentLabels: Record<StaffEmploymentState, Record<Locale, string>> = {
  invited: { en: "Invited", my: "ဖိတ်ကြားထားသည်" },
  active: { en: "Active", my: "တာဝန်ထမ်းဆောင်နေသည်" },
  on_leave: { en: "On leave", my: "ခွင့်ယူထားသည်" },
  suspended: { en: "Suspended", my: "ခေတ္တရပ်ဆိုင်းထားသည်" },
  departed: { en: "Departed", my: "အလုပ်မှထွက်ခွာပြီး" },
  archived: { en: "Archived", my: "မှတ်တမ်းသိမ်းထားသည်" },
};

export const staffAvailabilityLabels: Record<StaffAvailabilityState, Record<Locale, string>> = {
  available: { en: "Available", my: "ရရှိနိုင်သည်" },
  busy: { en: "Busy", my: "အလုပ်များနေသည်" },
  offline: { en: "Offline", my: "အော့ဖ်လိုင်း" },
  unavailable: { en: "Unavailable", my: "မရရှိနိုင်ပါ" },
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasRawKey(value: Record<string, unknown>): boolean {
  return Object.keys(value).some((key) => key.includes("_"));
}

export function isV2DepartmentId(value: string | null | undefined): value is V2DepartmentId {
  return typeof value === "string" && v2DepartmentIds.includes(value as V2DepartmentId);
}

export function isV2LifecycleStatus(value: string | null | undefined): value is V2LifecycleStatus {
  return typeof value === "string" && v2LifecycleStatuses.includes(value as V2LifecycleStatus);
}

export function isStaffEmploymentState(value: string | null | undefined): value is StaffEmploymentState {
  return typeof value === "string" && staffEmploymentStates.includes(value as StaffEmploymentState);
}

export function isStaffAvailabilityState(value: string | null | undefined): value is StaffAvailabilityState {
  return typeof value === "string" && staffAvailabilityStates.includes(value as StaffAvailabilityState);
}

export function readTicketVersion(value: unknown): TicketVersion {
  if (!isRecord(value) || hasRawKey(value)) throw new Error("ticket version metadata is not safely readable");
  const keys = ["schemaVersion", "workflowVersion", "taxonomyVersion"] as const;
  const present = keys.map((key) => Object.prototype.hasOwnProperty.call(value, key));
  if (!present.some(Boolean)) {
    const status = value.status;
    const department = value.departmentId;
    if (typeof status !== "string" || !v1Statuses.includes(status as (typeof v1Statuses)[number])) {
      throw new Error("missing version metadata is not proven V1");
    }
    if (department !== null && department !== undefined && (typeof department !== "string" || !v1DepartmentIds.includes(department as (typeof v1DepartmentIds)[number]))) {
      throw new Error("missing version metadata is not proven V1");
    }
    return "v1";
  }
  if (!present.every(Boolean)) throw new Error("version metadata is incomplete");
  const versions = keys.map((key) => value[key]);
  if (versions.every((version) => version === "v1")) return "v1";
  if (versions.every((version) => version === "v2")) return "v2";
  throw new Error("ticket version is unknown or inconsistent");
}

export function getV2DepartmentLabel(departmentId: V2DepartmentId, locale: Locale): string {
  return v2DepartmentLabels[departmentId][locale];
}

export function getV2LifecycleLabel(status: V2LifecycleStatus, locale: Locale): string {
  return v2LifecycleLabels[status][locale];
}

export function parseV2TicketContract(value: unknown): V2TicketContract {
  if (!isRecord(value) || hasRawKey(value)) throw new Error("V2 ticket contains unsafe keys");
  const allowed = ["schemaVersion", "workflowVersion", "taxonomyVersion", "categoryId", "status"];
  if (Object.keys(value).some((key) => !allowed.includes(key))) throw new Error("V2 ticket contains unknown fields");
  if (value.schemaVersion !== "v2" || value.workflowVersion !== "v2" || value.taxonomyVersion !== "v2") {
    throw new Error("V2 ticket version is unknown or inconsistent");
  }
  if (!isV2DepartmentId(typeof value.categoryId === "string" ? value.categoryId : null)) throw new Error("unknown V2 category");
  if (!isV2LifecycleStatus(typeof value.status === "string" ? value.status : null)) throw new Error("unknown V2 lifecycle status");
  return value as V2TicketContract;
}
