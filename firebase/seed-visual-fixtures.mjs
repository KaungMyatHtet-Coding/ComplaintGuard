import {
  SEEDED_IDENTITIES,
  assertSafeCommandOptions,
  buildFixturePlan,
  fixtureSummary,
  validateFixtureEnvironment,
} from "./visual-fixture-contract.mjs";

const options = process.argv.slice(2);
assertSafeCommandOptions(options, ["--create"]);
if (options.length !== 1 || options[0] !== "--create") {
  throw new Error("fixture_create_option_required");
}
const environment = validateFixtureEnvironment(process.env);

const [{ initializeTestEnvironment }, firestore] = await Promise.all([
  import("@firebase/rules-unit-testing"),
  import("firebase/firestore"),
]);

async function fetchAuthAccounts() {
  const accounts = [];
  const pageTokens = new Set();
  let nextPageToken = null;
  do {
    const query = new URLSearchParams({ maxResults: "1000" });
    if (nextPageToken) query.set("nextPageToken", nextPageToken);
    const response = await fetch(
      `http://${environment.auth.authority}/identitytoolkit.googleapis.com/v1/projects/${environment.projectId}/accounts:batchGet?${query}`,
      { headers: { Authorization: "Bearer owner" } },
    );
    if (!response.ok) throw new Error("fixture_auth_emulator_accounts_unavailable");
    const payload = await response.json();
    if (!payload || !Array.isArray(payload.users)) throw new Error("fixture_auth_emulator_accounts_invalid");
    accounts.push(...payload.users);
    nextPageToken = payload.nextPageToken ?? null;
    if (nextPageToken !== null && (typeof nextPageToken !== "string" || !nextPageToken || pageTokens.has(nextPageToken))) {
      throw new Error("fixture_auth_emulator_pagination_invalid");
    }
    if (nextPageToken) pageTokens.add(nextPageToken);
  } while (nextPageToken);
  return accounts;
}

function resolveIdentityUids(accounts) {
  const byEmail = new Map(accounts.map((account) => [account.email, account]));
  if (accounts.length !== SEEDED_IDENTITIES.length || byEmail.size !== SEEDED_IDENTITIES.length) {
    throw new Error("fixture_auth_baseline_unexpected");
  }
  const identityUids = {};
  for (const identity of SEEDED_IDENTITIES) {
    const account = byEmail.get(identity.email);
    if (!account || typeof account.localId !== "string" || !account.localId) {
      throw new Error(`fixture_auth_identity_missing:${identity.key}`);
    }
    identityUids[identity.key] = account.localId;
  }
  if (new Set(Object.values(identityUids)).size !== SEEDED_IDENTITIES.length) {
    throw new Error("fixture_auth_identity_duplicate");
  }
  return identityUids;
}

function normalize(value) {
  if (value instanceof Date) return value.toISOString();
  if (value && typeof value.toDate === "function") return value.toDate().toISOString();
  if (Array.isArray(value)) return value.map(normalize);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, normalize(value[key])]));
  }
  return value;
}

function exactEqual(actual, expected) {
  return JSON.stringify(normalize(actual)) === JSON.stringify(normalize(expected));
}

async function inspectFixtureState(db, plan) {
  const profileValidity = await Promise.all(SEEDED_IDENTITIES.map(async (identity) => {
    const uid = plan.identityUids[identity.key];
    const snapshot = await firestore.getDoc(firestore.doc(db, "users", uid));
    const data = snapshot.data();
    return snapshot.exists() && data?.email === identity.email && data?.role === identity.role
      && data?.active === true && data?.departmentId === identity.departmentId && data?.locale === identity.locale
      && typeof data?.createdAt?.toDate === "function" && typeof data?.updatedAt?.toDate === "function";
  }));
  if (profileValidity.some((valid) => !valid)) throw new Error("fixture_profile_baseline_invalid");

  const [profiles, tickets, feedback, metadata, messages, events, actions] = await Promise.all([
    firestore.getDocs(firestore.collection(db, "users")),
    firestore.getDocs(firestore.collection(db, "tickets")),
    firestore.getDocs(firestore.collection(db, "feedback")),
    firestore.getDocs(firestore.collection(db, "fixtureMeta")),
    firestore.getDocs(firestore.collectionGroup(db, "messages")),
    firestore.getDocs(firestore.collectionGroup(db, "events")),
    firestore.getDocs(firestore.collectionGroup(db, "actions")),
  ]);
  if (profiles.size !== SEEDED_IDENTITIES.length) throw new Error("fixture_profile_baseline_unexpected");
  const marker = metadata.docs.find((entry) => entry.id === plan.summary.fixtureVersion);
  return { tickets, feedback, metadata, messages, events, actions, marker };
}

async function assertSubcollectionsExact(db, plan) {
  const ticketIds = plan.records
    .filter((entry) => /^tickets\/[^/]+$/u.test(entry.path))
    .map((entry) => entry.path.split("/")[1]);
  for (const ticketId of ticketIds) {
    for (const collectionName of ["messages", "events", "actions"]) {
      const expected = plan.records.filter((entry) => entry.path.startsWith(`tickets/${ticketId}/${collectionName}/`));
      const snapshots = await firestore.getDocs(firestore.collection(db, "tickets", ticketId, collectionName));
      if (snapshots.size !== expected.length) throw new Error("fixture_existing_subcollection_conflict");
    }
  }
}

async function assertExistingFixtureExact(db, plan, state) {
  if (!state.marker || state.metadata.size !== 1) throw new Error("fixture_marker_invalid");
  if (!exactEqual(state.marker.data(), plan.records.at(-1).data)) throw new Error("fixture_marker_conflict");
  if (state.tickets.size !== plan.summary.ticketCount || state.feedback.size !== plan.summary.feedbackCount) {
    throw new Error("fixture_existing_counts_invalid");
  }
  if (state.messages.size !== plan.summary.messageCount || state.events.size !== plan.summary.eventCount || state.actions.size !== 0) {
    throw new Error("fixture_existing_subcollection_counts_invalid");
  }
  await assertSubcollectionsExact(db, plan);
  for (const entry of plan.records) {
    const snapshot = await firestore.getDoc(firestore.doc(db, ...entry.path.split("/")));
    if (!snapshot.exists() || !exactEqual(snapshot.data(), entry.data)) {
      throw new Error("fixture_existing_record_conflict");
    }
  }
}

async function assertFixtureNamespacesEmpty(db, plan) {
  const ticketIds = plan.records
    .filter((entry) => /^tickets\/[^/]+$/u.test(entry.path))
    .map((entry) => entry.path.split("/")[1]);
  for (const ticketId of ticketIds) {
    for (const collectionName of ["messages", "events", "actions"]) {
      const snapshots = await firestore.getDocs(firestore.collection(db, "tickets", ticketId, collectionName));
      if (snapshots.size) throw new Error("fixture_nonempty_namespace_rejected");
    }
  }
}

const accounts = await fetchAuthAccounts();
const identityUids = resolveIdentityUids(accounts);
const fixturePlan = buildFixturePlan(identityUids);
const plan = { ...fixturePlan, identityUids };
const testEnvironment = await initializeTestEnvironment({
  projectId: environment.projectId,
  firestore: { host: environment.firestore.host, port: environment.firestore.port },
});

try {
  let result;
  await testEnvironment.withSecurityRulesDisabled(async (context) => {
    const db = context.firestore();
    const state = await inspectFixtureState(db, plan);
    if (state.marker) {
      await assertExistingFixtureExact(db, plan, state);
      result = "already_verified";
      return;
    }
    if (state.tickets.size || state.feedback.size || state.metadata.size || state.messages.size || state.events.size || state.actions.size) {
      throw new Error("fixture_nonempty_baseline_rejected");
    }
    await assertFixtureNamespacesEmpty(db, plan);
    const batch = firestore.writeBatch(db);
    for (const entry of plan.records) {
      batch.set(firestore.doc(db, ...entry.path.split("/")), entry.data);
    }
    await batch.commit();
    result = "created";
  });
  if (result !== "created" && result !== "already_verified") {
    throw new Error("fixture_operation_result_missing");
  }
  const summary = fixtureSummary(fixturePlan.records);
  console.log(`Fixture ${result}: ${summary.fixtureVersion} (${summary.recordCount} records).`);
} finally {
  await testEnvironment.cleanup();
}
