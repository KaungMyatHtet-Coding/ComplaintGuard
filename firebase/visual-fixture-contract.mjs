import { createHash } from "node:crypto";

export const FIXTURE_VERSION = "day25-visual-fixture-v1";
export const DEMO_PROJECT_ID = "demo-complaintguard";

export const DEPARTMENT_IDS = Object.freeze([
  "transfer_payment",
  "account_support",
  "card_atm",
  "fraud_security",
  "loan_credit",
  "general_support",
]);

export const SEEDED_IDENTITIES = Object.freeze([
  { key: "customer", email: "customer@complaintguard.test", role: "customer", departmentId: null, locale: "en" },
  { key: "customerTwo", email: "customer.two@complaintguard.test", role: "customer", departmentId: null, locale: "en" },
  { key: "customerThree", email: "customer.three@complaintguard.test", role: "customer", departmentId: null, locale: "en" },
  { key: "customerFour", email: "customer.four@complaintguard.test", role: "customer", departmentId: null, locale: "en" },
  { key: "staffFraud", email: "staff.fraud@complaintguard.test", role: "staff", departmentId: "fraud_security", locale: "en" },
  { key: "staffCard", email: "staff.card@complaintguard.test", role: "staff", departmentId: "card_atm", locale: "en" },
  { key: "staffTransfer", email: "staff.transfer@complaintguard.test", role: "staff", departmentId: "transfer_payment", locale: "en" },
  { key: "staffAccount", email: "staff.account@complaintguard.test", role: "staff", departmentId: "account_support", locale: "en" },
  { key: "staffLoan", email: "staff.loan@complaintguard.test", role: "staff", departmentId: "loan_credit", locale: "en" },
  { key: "staffGeneral", email: "staff.general@complaintguard.test", role: "staff", departmentId: "general_support", locale: "en" },
  { key: "manager", email: "manager@complaintguard.test", role: "manager", departmentId: null, locale: "en" },
]);

const FIXTURE_TIMESTAMPS = Object.freeze({
  customerHistory: "2026-08-01T09:00:00.000Z",
  customerActive: "2026-08-10T09:00:00.000Z",
  cardTriaged: "2026-08-09T09:00:00.000Z",
  cardAwaiting: "2026-08-08T09:00:00.000Z",
  cardDetail: "2026-08-07T09:00:00.000Z",
  transfer: "2026-08-06T09:00:00.000Z",
  account: "2026-08-05T09:00:00.000Z",
  loan: "2026-08-04T09:00:00.000Z",
  general: "2026-08-03T09:00:00.000Z",
  manualCard: "2026-08-11T08:00:00.000Z",
  manualTransfer: "2026-08-11T07:00:00.000Z",
});

const LONG_TOKEN = "SyntheticVisualVerificationStringWithoutSpacesForResponsiveWrapping".repeat(4);

const TICKET_IDS = Object.freeze({
  customerHistory: "day25-customer-history-card-atm-reference-with-a-deliberately-long-unbroken-synthetic-identifier-001",
  customerActive: "day25-customer-detail-fraud-security-reference-with-a-deliberately-long-unbroken-synthetic-identifier-002",
  cardTriaged: "day25-card-queue-triaged-reference-with-a-deliberately-long-unbroken-synthetic-identifier-003",
  cardAwaiting: "day25-card-queue-awaiting-reference-with-a-deliberately-long-unbroken-synthetic-identifier-004",
  cardDetail: "day25-card-detail-reference-with-a-deliberately-long-unbroken-synthetic-identifier-005",
  transfer: "day25-transfer-payment-queue-reference-with-a-deliberately-long-unbroken-synthetic-identifier-006",
  account: "day25-account-support-queue-reference-with-a-deliberately-long-unbroken-synthetic-identifier-007",
  loan: "day25-loan-credit-queue-reference-with-a-deliberately-long-unbroken-synthetic-identifier-008",
  general: "day25-general-support-queue-reference-with-a-deliberately-long-unbroken-synthetic-identifier-009",
  manualCard: "day25-manager-manual-card-review-reference-with-a-deliberately-long-unbroken-synthetic-identifier-010",
  manualTransfer: "day25-manager-manual-transfer-review-reference-with-a-deliberately-long-unbroken-synthetic-identifier-011",
});

const EXPECTED_IDENTITY_KEYS = Object.freeze(SEEDED_IDENTITIES.map((identity) => identity.key));

function timestamp(key) {
  return new Date(FIXTURE_TIMESTAMPS[key]);
}

function ticket({
  customerId,
  departmentId,
  assignedStaffId,
  status,
  priority,
  predictedDepartmentId,
  predictionConfidence,
  routingSource,
  createdAt,
  complaintText,
  inputLocale = "en",
  resolvedAt = null,
  resolutionSummary = null,
  manualReviewReason = null,
  feedback = null,
}) {
  const result = {
    customerId,
    complaintText,
    inputLocale,
    departmentId,
    assignedStaffId,
    status,
    priority,
    predictedDepartmentId,
    predictionConfidence,
    routingSource,
    detectedLanguage: inputLocale,
    predictionModelVersion: routingSource === "pending" ? null : "v1",
    manualReviewReason,
    escalated: false,
    resolutionSummary,
    createdAt,
    updatedAt: resolvedAt ?? createdAt,
    resolvedAt,
  };
  if (feedback) result.feedback = feedback;
  return result;
}

function record(path, data) {
  return Object.freeze({ path, data: Object.freeze(data) });
}

function assertIdentityUids(identityUids) {
  if (!identityUids || typeof identityUids !== "object") {
    throw new Error("fixture_identity_uids_required");
  }
  for (const key of EXPECTED_IDENTITY_KEYS) {
    if (typeof identityUids[key] !== "string" || !identityUids[key].trim()) {
      throw new Error(`fixture_identity_uid_missing:${key}`);
    }
  }
  if (new Set(EXPECTED_IDENTITY_KEYS.map((key) => identityUids[key])).size !== EXPECTED_IDENTITY_KEYS.length) {
    throw new Error("fixture_identity_uids_duplicate");
  }
}

function buildCoreRecords(identityUids) {
  const ids = identityUids;
  const records = [
    record(`tickets/${TICKET_IDS.customerHistory}`, ticket({
      customerId: ids.customer,
      departmentId: "card_atm",
      assignedStaffId: ids.staffCard,
      status: "resolved",
      priority: "normal",
      predictedDepartmentId: "card_atm",
      predictionConfidence: 0.93,
      routingSource: "model",
      createdAt: timestamp("customerHistory"),
      resolvedAt: new Date("2026-08-02T09:00:00.000Z"),
      resolutionSummary: "Synthetic resolved card support example.",
      complaintText: `Synthetic card support history example ${LONG_TOKEN}`,
      feedback: {
        rating: 5,
        comments: "Synthetic feedback for visual verification.",
        submittedAt: new Date("2026-08-02T10:00:00.000Z"),
      },
    })),
    record(`tickets/${TICKET_IDS.customerActive}`, ticket({
      customerId: ids.customer,
      departmentId: "fraud_security",
      assignedStaffId: ids.staffFraud,
      status: "in_progress",
      priority: "high",
      predictedDepartmentId: "fraud_security",
      predictionConfidence: 0.91,
      routingSource: "model",
      createdAt: timestamp("customerActive"),
      complaintText: `Synthetic active fraud support detail ${LONG_TOKEN}`,
    })),
    record(`tickets/${TICKET_IDS.cardTriaged}`, ticket({
      customerId: ids.customerTwo,
      departmentId: "card_atm",
      assignedStaffId: ids.staffCard,
      status: "triaged",
      priority: "normal",
      predictedDepartmentId: "card_atm",
      predictionConfidence: 0.88,
      routingSource: "model",
      createdAt: timestamp("cardTriaged"),
      complaintText: "Synthetic card queue triage example.",
    })),
    record(`tickets/${TICKET_IDS.cardAwaiting}`, ticket({
      customerId: ids.customerThree,
      departmentId: "card_atm",
      assignedStaffId: ids.staffCard,
      status: "awaiting_customer",
      priority: "high",
      predictedDepartmentId: "card_atm",
      predictionConfidence: 0.86,
      routingSource: "model",
      createdAt: timestamp("cardAwaiting"),
      complaintText: "Synthetic card queue awaiting customer example.",
    })),
    record(`tickets/${TICKET_IDS.cardDetail}`, ticket({
      customerId: ids.customerFour,
      departmentId: "card_atm",
      assignedStaffId: ids.staffCard,
      status: "in_progress",
      priority: "urgent",
      predictedDepartmentId: "card_atm",
      predictionConfidence: 0.84,
      routingSource: "model",
      createdAt: timestamp("cardDetail"),
      complaintText: `Synthetic staff detail content ${LONG_TOKEN}`,
    })),
    record(`tickets/${TICKET_IDS.transfer}`, ticket({
      customerId: ids.customerTwo,
      departmentId: "transfer_payment",
      assignedStaffId: ids.staffTransfer,
      status: "triaged",
      priority: "normal",
      predictedDepartmentId: "transfer_payment",
      predictionConfidence: 0.89,
      routingSource: "model",
      createdAt: timestamp("transfer"),
      complaintText: "Synthetic transfer and payment queue example.",
    })),
    record(`tickets/${TICKET_IDS.account}`, ticket({
      customerId: ids.customerThree,
      departmentId: "account_support",
      assignedStaffId: ids.staffAccount,
      status: "resolved",
      priority: "normal",
      predictedDepartmentId: "account_support",
      predictionConfidence: 0.9,
      routingSource: "model",
      createdAt: timestamp("account"),
      resolvedAt: new Date("2026-08-06T09:00:00.000Z"),
      resolutionSummary: "Synthetic resolved account support example.",
      complaintText: "Synthetic account support queue example.",
    })),
    record(`tickets/${TICKET_IDS.loan}`, ticket({
      customerId: ids.customerFour,
      departmentId: "loan_credit",
      assignedStaffId: ids.staffLoan,
      status: "triaged",
      priority: "high",
      predictedDepartmentId: "loan_credit",
      predictionConfidence: 0.87,
      routingSource: "model",
      createdAt: timestamp("loan"),
      complaintText: "Synthetic loan and credit queue example.",
    })),
    record(`tickets/${TICKET_IDS.general}`, ticket({
      customerId: ids.customerTwo,
      departmentId: "general_support",
      assignedStaffId: ids.staffGeneral,
      status: "triaged",
      priority: "normal",
      predictedDepartmentId: "general_support",
      predictionConfidence: 0.82,
      routingSource: "model",
      createdAt: timestamp("general"),
      complaintText: "Synthetic general support queue example.",
    })),
    record(`tickets/${TICKET_IDS.manualCard}`, ticket({
      customerId: ids.customerThree,
      departmentId: null,
      assignedStaffId: null,
      status: "submitted",
      priority: "normal",
      predictedDepartmentId: "card_atm",
      predictionConfidence: 0.42,
      routingSource: "manual_review",
      createdAt: timestamp("manualCard"),
      complaintText: `Synthetic ambiguous manager review ${LONG_TOKEN}`,
      manualReviewReason: "low_classifier_confidence",
    })),
    record(`tickets/${TICKET_IDS.manualTransfer}`, ticket({
      customerId: ids.customerFour,
      departmentId: null,
      assignedStaffId: null,
      status: "submitted",
      priority: "normal",
      predictedDepartmentId: "transfer_payment",
      predictionConfidence: 0.49,
      routingSource: "manual_review",
      createdAt: timestamp("manualTransfer"),
      complaintText: "Synthetic ambiguous transfer manager review example.",
      manualReviewReason: "low_classifier_confidence",
    })),
    record(`tickets/${TICKET_IDS.customerActive}/messages/day25-customer-active-staff-message`, {
      authorId: ids.staffFraud,
      authorRole: "staff",
      body: `Synthetic staff message for responsive customer detail ${LONG_TOKEN}`,
      visibility: "participants",
      createdAt: new Date("2026-08-10T10:00:00.000Z"),
    }),
    record(`tickets/${TICKET_IDS.customerActive}/messages/day25-customer-active-customer-message`, {
      authorId: ids.customer,
      authorRole: "customer",
      body: `Synthetic customer message for responsive detail ${LONG_TOKEN}`,
      visibility: "participants",
      createdAt: new Date("2026-08-10T11:00:00.000Z"),
    }),
    record(`tickets/${TICKET_IDS.cardDetail}/messages/day25-card-detail-customer-message`, {
      authorId: ids.customerFour,
      authorRole: "customer",
      body: `Synthetic long unbroken staff queue message ${LONG_TOKEN}`,
      visibility: "participants",
      createdAt: new Date("2026-08-07T10:00:00.000Z"),
    }),
    record(`tickets/${TICKET_IDS.cardDetail}/messages/day25-card-detail-staff-message`, {
      authorId: ids.staffCard,
      authorRole: "staff",
      body: "Synthetic staff acknowledgement for selected queue detail.",
      visibility: "participants",
      createdAt: new Date("2026-08-07T11:00:00.000Z"),
    }),
    record(`tickets/${TICKET_IDS.customerActive}/events/day25-customer-active-model-routing`, {
      ticketId: TICKET_IDS.customerActive,
      type: "model_prediction",
      actorId: "trusted_ml_v1",
      actorRole: "system",
      fromValue: null,
      toValue: "fraud_security",
      predictedDepartmentId: "fraud_security",
      predictionConfidence: 0.91,
      routingSource: "model",
      createdAt: new Date("2026-08-10T09:01:00.000Z"),
    }),
    record(`tickets/${TICKET_IDS.cardDetail}/events/day25-card-detail-model-routing`, {
      ticketId: TICKET_IDS.cardDetail,
      type: "model_prediction",
      actorId: "trusted_ml_v1",
      actorRole: "system",
      fromValue: null,
      toValue: "card_atm",
      predictedDepartmentId: "card_atm",
      predictionConfidence: 0.84,
      routingSource: "model",
      createdAt: new Date("2026-08-07T09:01:00.000Z"),
    }),
    record(`tickets/${TICKET_IDS.cardDetail}/events/day25-card-detail-status-transition`, {
      type: "status_transition",
      actorId: ids.staffCard,
      actorRole: "staff",
      fromValue: "triaged",
      toValue: "in_progress",
      createdAt: new Date("2026-08-07T09:30:00.000Z"),
    }),
    record(`tickets/${TICKET_IDS.customerHistory}/events/day25-customer-history-resolution`, {
      type: "status_transition",
      actorId: ids.staffCard,
      actorRole: "staff",
      fromValue: "in_progress",
      toValue: "resolved",
      createdAt: new Date("2026-08-02T09:00:00.000Z"),
    }),
    record(`feedback/fb_${TICKET_IDS.customerHistory}`, {
      ticketId: TICKET_IDS.customerHistory,
      customerId: ids.customer,
      rating: 5,
      comments: "Synthetic feedback for visual verification.",
      createdAt: new Date("2026-08-02T10:00:00.000Z"),
    }),
  ];

  return records;
}

function contractValue(value) {
  if (value instanceof Date) return value.toISOString();
  if (Array.isArray(value)) return value.map(contractValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, contractValue(value[key])]));
  }
  return value;
}

export function canonicalFixtureJson(value) {
  return JSON.stringify(contractValue(value));
}

function digest(value) {
  return createHash("sha256").update(canonicalFixtureJson(value)).digest("hex");
}

const DIGEST_PLACEHOLDER_UIDS = Object.freeze(
  Object.fromEntries(EXPECTED_IDENTITY_KEYS.map((key) => [key, `fixture-${key}-uid`])),
);

export const CONTRACT_DIGEST = digest({
  fixtureVersion: FIXTURE_VERSION,
  records: buildCoreRecords(DIGEST_PLACEHOLDER_UIDS),
});

export function buildFixturePlan(identityUids) {
  assertIdentityUids(identityUids);
  const records = buildCoreRecords(identityUids);
  const summary = summarizeRecords(records);
  records.push(record(`fixtureMeta/${FIXTURE_VERSION}`, {
    fixtureVersion: FIXTURE_VERSION,
    contractDigest: CONTRACT_DIGEST,
    generatedAt: new Date("2026-08-11T12:00:00.000Z"),
    ticketCount: summary.ticketCount,
    messageCount: summary.messageCount,
    eventCount: summary.eventCount,
    feedbackCount: summary.feedbackCount,
  }));
  validateFixturePlan(records);
  return Object.freeze({ records: Object.freeze(records), summary: fixtureSummary(records) });
}

export function summarizeRecords(records) {
  return {
    ticketCount: records.filter((entry) => /^tickets\/[^/]+$/u.test(entry.path)).length,
    messageCount: records.filter((entry) => /\/messages\//u.test(entry.path)).length,
    eventCount: records.filter((entry) => /\/events\//u.test(entry.path)).length,
    feedbackCount: records.filter((entry) => entry.path.startsWith("feedback/")).length,
  };
}

export function fixtureSummary(records) {
  const counts = summarizeRecords(records);
  return Object.freeze({
    fixtureVersion: FIXTURE_VERSION,
    contractDigest: CONTRACT_DIGEST,
    ...counts,
    recordCount: records.length,
  });
}

export function validateFixturePlan(records) {
  const paths = new Set();
  for (const entry of records) {
    if (!entry || typeof entry.path !== "string" || !entry.data || typeof entry.data !== "object") {
      throw new Error("fixture_record_invalid");
    }
    if (paths.has(entry.path)) throw new Error(`fixture_duplicate_path:${entry.path}`);
    paths.add(entry.path);
    const segments = entry.path.split("/");
    if (segments.length % 2 !== 0) throw new Error("fixture_document_path_invalid");
    for (const segment of segments) {
      if (!isValidFirestoreDocumentId(segment)) throw new Error(`fixture_document_id_invalid:${segment}`);
    }
  }
  const counts = summarizeRecords(records);
  if (counts.ticketCount !== 11 || counts.messageCount !== 4 || counts.eventCount !== 4 || counts.feedbackCount !== 1) {
    throw new Error("fixture_record_counts_invalid");
  }
  const tickets = records.filter((entry) => /^tickets\/[^/]+$/u.test(entry.path));
  const departments = new Set(tickets.map((entry) => entry.data.departmentId).filter(Boolean));
  if (DEPARTMENT_IDS.some((departmentId) => !departments.has(departmentId))) {
    throw new Error("fixture_departments_incomplete");
  }
  const manualReview = tickets.filter((entry) => entry.data.routingSource === "manual_review");
  if (manualReview.length !== 2 || manualReview.some((entry) => entry.data.departmentId !== null || entry.data.assignedStaffId !== null || entry.data.status !== "submitted")) {
    throw new Error("fixture_manual_review_invalid");
  }
  return true;
}

export function isValidFirestoreDocumentId(value) {
  return typeof value === "string" && value.length > 0 && new TextEncoder().encode(value).byteLength <= 1500
    && !value.includes("/") && value !== "." && value !== ".." && !/^__.*__$/u.test(value);
}

export function validateFixtureEnvironment(environment = process.env) {
  const projectValues = [environment.GCLOUD_PROJECT, environment.GOOGLE_CLOUD_PROJECT]
    .filter((value) => typeof value === "string" && value.trim());
  if (!projectValues.length) throw new Error("fixture_project_id_required");
  if (new Set(projectValues).size !== 1 || projectValues[0] !== DEMO_PROJECT_ID) {
    throw new Error("fixture_project_id_invalid");
  }
  const firestore = parseLoopbackEmulatorHost(environment.FIRESTORE_EMULATOR_HOST, "firestore");
  const auth = parseLoopbackEmulatorHost(environment.FIREBASE_AUTH_EMULATOR_HOST, "auth");
  if (firestore.port === auth.port) throw new Error("fixture_emulator_hosts_conflict");
  return Object.freeze({
    projectId: DEMO_PROJECT_ID,
    firestore,
    auth,
  });
}

export function parseLoopbackEmulatorHost(value, name) {
  if (typeof value !== "string" || !value || value !== value.trim()) throw new Error(`fixture_${name}_emulator_host_required`);
  const match = /^(?<host>127\.0\.0\.1|localhost):(?<port>\d{1,5})$/u.exec(value)
    ?? /^\[(?<host>::1)\]:(?<port>\d{1,5})$/u.exec(value);
  if (!match?.groups) throw new Error(`fixture_${name}_emulator_host_invalid`);
  const port = Number(match.groups.port);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error(`fixture_${name}_emulator_port_invalid`);
  return Object.freeze({ host: match.groups.host, port, authority: value });
}

export function assertSafeCommandOptions(argv, allowedOptions) {
  for (const option of argv) {
    if (typeof option !== "string" || !allowedOptions.includes(option)) {
      throw new Error("fixture_command_option_rejected");
    }
    if (/--(?:reset|force|overwrite|clear|delete|import|export)/iu.test(option)) {
      throw new Error("fixture_destructive_option_rejected");
    }
  }
}

export function containsSensitiveFixtureContent(value) {
  const text = JSON.stringify(contractValue(value));
  return /password|token|secret|private[_ -]?key|\b(?:\d[ -]?){13,19}\b/iu.test(text);
}
