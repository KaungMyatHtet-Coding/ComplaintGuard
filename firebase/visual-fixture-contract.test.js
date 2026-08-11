import assert from "node:assert/strict";
import test from "node:test";

import {
  CONTRACT_DIGEST,
  DEPARTMENT_IDS,
  FIXTURE_VERSION,
  SEEDED_IDENTITIES,
  assertSafeCommandOptions,
  buildFixturePlan,
  canonicalFixtureJson,
  containsSensitiveFixtureContent,
  fixtureSummary,
  isValidFirestoreDocumentId,
  validateFixturePlan,
  validateFixtureEnvironment,
} from "./visual-fixture-contract.mjs";

const identityUids = Object.freeze(
  Object.fromEntries(SEEDED_IDENTITIES.map((identity) => [identity.key, `uid-${identity.key}`])),
);

test("the pure contract import performs no network work", async () => {
  const originalFetch = globalThis.fetch;
  let fetchCalled = false;
  globalThis.fetch = async () => {
    fetchCalled = true;
    throw new Error("network must not be called");
  };
  try {
    await import(`./visual-fixture-contract.mjs?pure-import-${Date.now()}`);
    assert.equal(fetchCalled, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("fixture plan is deterministic and contains the required visual records", () => {
  const first = buildFixturePlan(identityUids);
  const second = buildFixturePlan(identityUids);
  assert.equal(first.summary.fixtureVersion, FIXTURE_VERSION);
  assert.equal(first.summary.contractDigest, CONTRACT_DIGEST);
  assert.deepEqual(first.summary, second.summary);
  assert.equal(first.summary.ticketCount, 11);
  assert.equal(first.summary.messageCount, 4);
  assert.equal(first.summary.eventCount, 4);
  assert.equal(first.summary.feedbackCount, 1);
  assert.equal(first.summary.recordCount, 21);
  assert.deepEqual(first.records.map((entry) => entry.path), second.records.map((entry) => entry.path));
  assert.deepEqual(first.records.map((entry) => entry.data), second.records.map((entry) => entry.data));
});

test("fixture tickets cover all departments and preserve manual-review routing invariants", () => {
  const plan = buildFixturePlan(identityUids);
  const tickets = plan.records.filter((entry) => /^tickets\/[^/]+$/u.test(entry.path));
  assert.deepEqual(
    [...new Set(tickets.map((entry) => entry.data.departmentId).filter(Boolean))].sort(),
    [...DEPARTMENT_IDS].sort(),
  );
  const manualReview = tickets.filter((entry) => entry.data.routingSource === "manual_review");
  assert.equal(manualReview.length, 2);
  for (const entry of manualReview) {
    assert.equal(entry.data.departmentId, null);
    assert.equal(entry.data.assignedStaffId, null);
    assert.equal(entry.data.status, "submitted");
    assert.equal(typeof entry.data.predictionConfidence, "number");
    assert.ok(entry.data.predictionConfidence < 0.6);
  }
  assert.equal(tickets.filter((entry) => entry.data.customerId === identityUids.customer).length, 2);
  assert.equal(tickets.filter((entry) => entry.data.departmentId === "card_atm").length, 4);
  assert.ok(tickets.some((entry) => entry.data.status === "resolved"));
  assert.ok(tickets.some((entry) => entry.data.status === "in_progress"));
  assert.ok(tickets.some((entry) => entry.data.status === "awaiting_customer"));
  assert.ok(tickets.every((entry) => ["submitted", "triaged", "in_progress", "awaiting_customer", "resolved"].includes(entry.data.status)));
  assert.ok(tickets.every((entry) => ["model", "manual_review"].includes(entry.data.routingSource)));
});

test("planned paths and fixed dates are valid, unique, and suitable for Firestore", () => {
  const plan = buildFixturePlan(identityUids);
  const paths = plan.records.map((entry) => entry.path);
  assert.equal(new Set(paths).size, paths.length);
  for (const path of paths) {
    for (const segment of path.split("/")) {
      assert.equal(isValidFirestoreDocumentId(segment), true);
      assert.ok(Buffer.byteLength(segment, "utf8") < 1500);
    }
  }
  const ticketRecords = plan.records.filter((entry) => /^tickets\/[^/]+$/u.test(entry.path));
  assert.ok(ticketRecords.some((entry) => entry.path.length > 100));
  assert.ok(ticketRecords.some((entry) => entry.data.complaintText.includes("SyntheticVisualVerificationStringWithoutSpaces")));
  for (const entry of plan.records) {
    for (const value of Object.values(entry.data)) {
      if (value instanceof Date) assert.ok(Number.isFinite(value.getTime()));
    }
  }
});

test("the contract creates matching ownership, staff, messages, events, and feedback placeholders", () => {
  const plan = buildFixturePlan(identityUids);
  const customers = new Set([identityUids.customer, identityUids.customerTwo, identityUids.customerThree, identityUids.customerFour]);
  const staff = new Set([identityUids.staffFraud, identityUids.staffCard, identityUids.staffTransfer, identityUids.staffAccount, identityUids.staffLoan, identityUids.staffGeneral]);
  const tickets = plan.records.filter((entry) => /^tickets\/[^/]+$/u.test(entry.path));
  assert.ok(tickets.every((entry) => customers.has(entry.data.customerId)));
  assert.ok(tickets.filter((entry) => entry.data.departmentId !== null).every((entry) => staff.has(entry.data.assignedStaffId)));
  assert.ok(plan.records.some((entry) => /\/messages\//u.test(entry.path) && entry.data.visibility === "participants"));
  assert.ok(plan.records.some((entry) => /\/events\//u.test(entry.path) && typeof entry.data.actorRole === "string"));
  assert.ok(plan.records.some((entry) => entry.path.startsWith("feedback/") && entry.data.rating === 5));
  assert.ok(plan.records.some((entry) => entry.data.feedback?.submittedAt instanceof Date));
});

test("missing identity placeholders and unknown document IDs fail safely", () => {
  assert.throws(() => buildFixturePlan({ customer: "uid-customer" }), /fixture_identity_uid_missing/u);
  assert.throws(() => buildFixturePlan(Object.fromEntries(SEEDED_IDENTITIES.map((identity) => [identity.key, "duplicate-uid"]))), /fixture_identity_uids_duplicate/u);
  assert.equal(isValidFirestoreDocumentId(""), false);
  assert.equal(isValidFirestoreDocumentId("ticket/with/slash"), false);
  assert.equal(isValidFirestoreDocumentId(".."), false);
  assert.equal(isValidFirestoreDocumentId("__reserved__"), false);
  assert.equal(isValidFirestoreDocumentId(String.fromCodePoint(0x1f600).repeat(376)), false);
  const plan = buildFixturePlan(identityUids);
  assert.throws(() => validateFixturePlan([plan.records[0], plan.records[0]]), /fixture_duplicate_path/u);
  assert.throws(() => validateFixturePlan([{ path: "tickets", data: {} }]), /fixture_document_path_invalid/u);
});

test("contract digest and public summaries remain stable and secret-free", () => {
  const plan = buildFixturePlan(identityUids);
  const differentRuntimeUids = Object.fromEntries(SEEDED_IDENTITIES.map((identity) => [identity.key, `different-${identity.key}`]));
  assert.match(CONTRACT_DIGEST, /^[a-f0-9]{64}$/u);
  assert.deepEqual(fixtureSummary(plan.records), plan.summary);
  assert.equal(buildFixturePlan(differentRuntimeUids).summary.contractDigest, CONTRACT_DIGEST);
  assert.equal(canonicalFixtureJson({ z: [3, 2, 1], a: { b: 2, a: 1 } }), canonicalFixtureJson({ a: { a: 1, b: 2 }, z: [3, 2, 1] }));
  assert.equal(containsSensitiveFixtureContent(plan.records), false);
  assert.equal(containsSensitiveFixtureContent(plan.summary), false);
  assert.doesNotMatch(JSON.stringify(plan.summary), /customer@|password|token|secret/iu);
});

test("environment validation accepts only explicit loopback demo-emulator settings", () => {
  const base = {
    GCLOUD_PROJECT: "demo-complaintguard",
    FIRESTORE_EMULATOR_HOST: "127.0.0.1:8185",
    FIREBASE_AUTH_EMULATOR_HOST: "localhost:9099",
  };
  assert.deepEqual(validateFixtureEnvironment(base), {
    projectId: "demo-complaintguard",
    firestore: { host: "127.0.0.1", port: 8185, authority: "127.0.0.1:8185" },
    auth: { host: "localhost", port: 9099, authority: "localhost:9099" },
  });
  assert.equal(validateFixtureEnvironment({ ...base, GCLOUD_PROJECT: undefined, GOOGLE_CLOUD_PROJECT: "demo-complaintguard" }).projectId, "demo-complaintguard");
  assert.equal(validateFixtureEnvironment({ ...base, FIRESTORE_EMULATOR_HOST: "[::1]:8185" }).firestore.host, "::1");
  for (const environment of [
    {},
    { ...base, GCLOUD_PROJECT: "other-project" },
    { ...base, GOOGLE_CLOUD_PROJECT: "conflicting-project" },
    { ...base, FIRESTORE_EMULATOR_HOST: "example.com:8185" },
    { ...base, FIRESTORE_EMULATOR_HOST: "http://127.0.0.1:8185" },
    { ...base, FIRESTORE_EMULATOR_HOST: "user@127.0.0.1:8185" },
    { ...base, FIRESTORE_EMULATOR_HOST: "127.0.0.1:8185?query=value" },
    { ...base, FIRESTORE_EMULATOR_HOST: "0.0.0.0:8185" },
    { ...base, FIRESTORE_EMULATOR_HOST: " 127.0.0.1:8185" },
    { ...base, FIREBASE_AUTH_EMULATOR_HOST: "127.0.0.1:not-a-port" },
    { ...base, FIREBASE_AUTH_EMULATOR_HOST: "127.0.0.1:0" },
    { ...base, FIREBASE_AUTH_EMULATOR_HOST: "127.0.0.1:65536" },
    { ...base, FIREBASE_AUTH_EMULATOR_HOST: "127.0.0.1:8185" },
    { ...base, FIREBASE_AUTH_EMULATOR_HOST: "localhost:8185" },
  ]) {
    assert.throws(() => validateFixtureEnvironment(environment));
  }
});

test("destructive and unknown command options are rejected", () => {
  assert.doesNotThrow(() => assertSafeCommandOptions(["--create"], ["--create"]));
  for (const option of ["--reset-firestore", "--reset-firestore=true", "--force", "--FORCE", "--overwrite", "--import", "--export-on-exit", "--create=value", "--CREATE", "--unknown"]) {
    assert.throws(() => assertSafeCommandOptions([option], ["--create"]));
  }
});
