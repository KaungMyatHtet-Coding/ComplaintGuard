import { randomBytes } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { initializeTestEnvironment } from "@firebase/rules-unit-testing";
import { doc, getDoc, serverTimestamp, setDoc } from "firebase/firestore";

const projectId = process.env.GCLOUD_PROJECT || "demo-complaintguard";
const authHost = process.env.FIREBASE_AUTH_EMULATOR_HOST || "127.0.0.1:9099";
const firestoreHost = process.env.FIRESTORE_EMULATOR_HOST || "127.0.0.1:8185";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const output = resolve(root, "firebase", ".firebase", "seeded-identities.json");
const resetFirestore = process.argv.includes("--reset-firestore");
const identities = [
  { key: "customer", email: "customer@complaintguard.test", role: "customer", locale: "en" },
  { key: "customerTwo", email: "customer.two@complaintguard.test", role: "customer", locale: "en" },
  { key: "customerThree", email: "customer.three@complaintguard.test", role: "customer", locale: "en" },
  { key: "customerFour", email: "customer.four@complaintguard.test", role: "customer", locale: "en" },
  { key: "staffFraud", email: "staff.fraud@complaintguard.test", role: "staff", departmentId: "fraud_security", locale: "en" },
  { key: "staffCard", email: "staff.card@complaintguard.test", role: "staff", departmentId: "card_atm", locale: "en" },
  { key: "staffTransfer", email: "staff.transfer@complaintguard.test", role: "staff", departmentId: "transfer_payment", locale: "en" },
  { key: "staffAccount", email: "staff.account@complaintguard.test", role: "staff", departmentId: "account_support", locale: "en" },
  { key: "staffLoan", email: "staff.loan@complaintguard.test", role: "staff", departmentId: "loan_credit", locale: "en" },
  { key: "staffGeneral", email: "staff.general@complaintguard.test", role: "staff", departmentId: "general_support", locale: "en" },
  { key: "manager", email: "manager@complaintguard.test", role: "manager", locale: "en" },
];

async function previousSeed() {
  try {
    const value = JSON.parse(await readFile(output, "utf8"));
    return value.projectId === projectId ? value : null;
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw new Error("emulator_seed_credentials_invalid", { cause: error });
  }
}

const previous = await previousSeed();
const previousPasswords = new Set(
  (previous?.identities ?? []).map((identity) => identity.password).filter(Boolean),
);
if (previousPasswords.size > 1) throw new Error("emulator_seed_passwords_inconsistent");
const password = previousPasswords.values().next().value ??
  `Cg-${randomBytes(18).toString("base64url")}!`;

const accountsResponse = await fetch(
  `http://${authHost}/identitytoolkit.googleapis.com/v1/projects/${projectId}/accounts:batchGet?maxResults=1000`,
  { headers: { Authorization: "Bearer owner" } },
);
if (!accountsResponse.ok) {
  throw new Error(`auth_emulator_list_failed:${accountsResponse.status}`);
}
const accounts = (await accountsResponse.json()).users ?? [];
const accountsByEmail = new Map(accounts.map((account) => [account.email, account]));
const previousByEmail = new Map(
  (previous?.identities ?? []).map((identity) => [identity.email, identity]),
);

for (const identity of identities) {
  const existing = accountsByEmail.get(identity.email);
  if (existing) {
    const known = previousByEmail.get(identity.email);
    if (!known?.password) {
      throw new Error(`auth_emulator_existing_credential_unknown:${identity.key}`);
    }
    const signInResponse = await fetch(
      `http://${authHost}/identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=emulator-only`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: identity.email,
          password: known.password,
          returnSecureToken: false,
        }),
      },
    );
    if (!signInResponse.ok) {
      throw new Error(`auth_emulator_existing_credential_mismatch:${identity.key}`);
    }
    identity.uid = existing.localId;
    identity.password = known.password;
    continue;
  }
  const response = await fetch(
    `http://${authHost}/identitytoolkit.googleapis.com/v1/accounts:signUp?key=emulator-only`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: identity.email, password, returnSecureToken: true }),
    },
  );
  if (!response.ok) throw new Error(`auth_emulator_seed_failed:${identity.key}`);
  const result = await response.json();
  identity.uid = result.localId;
  identity.password = password;
}

const [host, port] = firestoreHost.split(":");
const testEnvironment = await initializeTestEnvironment({
  projectId,
  firestore: { host, port: Number(port) },
});
if (resetFirestore) await testEnvironment.clearFirestore();
await testEnvironment.withSecurityRulesDisabled(async (context) => {
  for (const identity of identities) {
    const profileRef = doc(context.firestore(), "users", identity.uid);
    const existingProfile = await getDoc(profileRef);
    const existingData = existingProfile.data() ?? {};
    await setDoc(profileRef, {
      email: identity.email,
      displayName: existingData.displayName ?? `Emulator ${identity.key}`,
      role: identity.role,
      active: true,
      locale: identity.locale,
      departmentId: identity.departmentId ?? null,
      createdAt: existingData.createdAt ?? serverTimestamp(),
      updatedAt: serverTimestamp(),
    });
  }
});
await testEnvironment.cleanup();

await mkdir(dirname(output), { recursive: true });
await writeFile(output, JSON.stringify({ projectId, identities }, null, 2), "utf8");
console.log(`Seeded ${identities.length} emulator identities.`);
