import { translate, type Locale, type MessageKey } from "@/lib/i18n";

export const departmentIds = [
  "transfer_payment",
  "account_support",
  "card_atm",
  "fraud_security",
  "loan_credit",
  "general_support",
] as const;

export type DepartmentId = (typeof departmentIds)[number];

const departmentLabelKeys: Record<DepartmentId, MessageKey> = {
  transfer_payment: "departmentTransferPayment",
  account_support: "departmentAccountSupport",
  card_atm: "departmentCardAtm",
  fraud_security: "departmentFraudSecurity",
  loan_credit: "departmentLoanCredit",
  general_support: "departmentGeneralSupport",
};

export function isDepartmentId(value: string | null | undefined): value is DepartmentId {
  return Boolean(value && departmentIds.includes(value as DepartmentId));
}

export function getDepartmentLabel(
  departmentId: string | null | undefined,
  locale: Locale,
): string | null {
  return isDepartmentId(departmentId)
    ? translate(locale, departmentLabelKeys[departmentId])
    : null;
}
