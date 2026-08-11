import {
  SEEDED_IDENTITIES,
  assertSafeCommandOptions,
  buildFixturePlan,
  fixtureSummary,
  validateFixtureEnvironment,
} from "./visual-fixture-contract.mjs";

const options = process.argv.slice(2);
assertSafeCommandOptions(options, ["--verify"]);
if (options.length !== 1 || options[0] !== "--verify") {
  throw new Error("fixture_verify_option_required");
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

const accounts = await fetchAuthAccounts();
const identityUids = resolveIdentityUids(accounts);
const fixturePlan = buildFixturePlan(identityUids);
const testEnvironment = await initializeTestEnvironment({
  projectId: environment.projectId,
  firestore: { host: environment.firestore.host, port: environment.firestore.port },
});

try {
  await testEnvironment.withSecurityRulesDisabled(async (context) => {
    const db = context.firestore();
    const [profiles, tickets, feedback, metadata, messages, events, actions] = await Promise.all([
      firestore.getDocs(firestore.collection(db, "users")),
      firestore.getDocs(firestore.collection(db, "tickets")),
      firestore.getDocs(firestore.collection(db, "feedback")),
      firestore.getDocs(firestore.collection(db, "fixtureMeta")),
      firestore.getDocs(firestore.collectionGroup(db, "messages")),
      firestore.getDocs(firestore.collectionGroup(db, "events")),
      firestore.getDocs(firestore.collectionGroup(db, "actions")),
    ]);
    const marker = metadata.docs.find((entry) => entry.id === fixturePlan.summary.fixtureVersion);
    if (!marker || metadata.size !== 1 || !exactEqual(marker.data(), fixturePlan.records.at(-1).data)) {
      throw new Error("fixture_marker_invalid");
    }
    if (tickets.size !== fixturePlan.summary.ticketCount || feedback.size !== fixturePlan.summary.feedbackCount) {
      throw new Error("fixture_record_counts_invalid");
    }
    if (messages.size !== fixturePlan.summary.messageCount || events.size !== fixturePlan.summary.eventCount || actions.size !== 0) {
      throw new Error("fixture_subcollection_counts_invalid");
    }
    if (profiles.size !== SEEDED_IDENTITIES.length) throw new Error("fixture_profile_count_invalid");
    for (const identity of SEEDED_IDENTITIES) {
      const snapshot = await firestore.getDoc(firestore.doc(db, "users", identityUids[identity.key]));
      const profile = snapshot.data();
      if (!snapshot.exists() || profile?.email !== identity.email || profile?.role !== identity.role
        || profile?.active !== true || profile?.departmentId !== identity.departmentId || profile?.locale !== identity.locale
        || typeof profile?.createdAt?.toDate !== "function" || typeof profile?.updatedAt?.toDate !== "function") {
        throw new Error("fixture_profile_invalid");
      }
    }
    for (const entry of fixturePlan.records) {
      const snapshot = await firestore.getDoc(firestore.doc(db, ...entry.path.split("/")));
      if (!snapshot.exists() || !exactEqual(snapshot.data(), entry.data)) {
        throw new Error("fixture_record_invalid");
      }
    }
    const ticketIds = fixturePlan.records
      .filter((entry) => /^tickets\/[^/]+$/u.test(entry.path))
      .map((entry) => entry.path.split("/")[1]);
    for (const ticketId of ticketIds) {
      for (const collectionName of ["messages", "events", "actions"]) {
        const expected = fixturePlan.records.filter((entry) => entry.path.startsWith(`tickets/${ticketId}/${collectionName}/`));
        const snapshots = await firestore.getDocs(firestore.collection(db, "tickets", ticketId, collectionName));
        if (snapshots.size !== expected.length) throw new Error("fixture_subcollection_count_invalid");
      }
    }
  });
  const summary = fixtureSummary(fixturePlan.records);
  console.log(`Fixture verified: ${summary.fixtureVersion} (${summary.recordCount} records).`);
} finally {
  await testEnvironment.cleanup();
}
