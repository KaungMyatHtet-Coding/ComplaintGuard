import { randomBytes } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { initializeTestEnvironment } from "@firebase/rules-unit-testing";
import { doc, setDoc } from "firebase/firestore";

const projectId = process.env.GCLOUD_PROJECT || "demo-complaintguard";
const authHost = process.env.FIREBASE_AUTH_EMULATOR_HOST || "127.0.0.1:9099";
const firestoreHost = process.env.FIRESTORE_EMULATOR_HOST || "127.0.0.1:8185";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const output = resolve(root, "firebase", ".firebase", "seeded-identities.json");
const password = `Cg-${randomBytes(18).toString("base64url")}!`;
const identities = [
  { key: "customer", email: "customer@complaintguard.test", role: "customer", locale: "en" },
  { key: "staffFraud", email: "staff.fraud@complaintguard.test", role: "staff", departmentId: "fraud_security", locale: "en" },
  { key: "staffCard", email: "staff.card@complaintguard.test", role: "staff", departmentId: "card_atm", locale: "en" },
  { key: "manager", email: "manager@complaintguard.test", role: "manager", locale: "en" },
];

await fetch(`http://${authHost}/emulator/v1/projects/${projectId}/accounts`, {
  method: "DELETE",
});

for (const identity of identities) {
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
await testEnvironment.clearFirestore();
await testEnvironment.withSecurityRulesDisabled(async (context) => {
  for (const identity of identities) {
    await setDoc(doc(context.firestore(), "users", identity.uid), {
      email: identity.email,
      displayName: `Emulator ${identity.key}`,
      role: identity.role,
      active: true,
      locale: identity.locale,
      departmentId: identity.departmentId ?? null,
    });
  }
});
await testEnvironment.cleanup();

await mkdir(dirname(output), { recursive: true });
await writeFile(output, JSON.stringify({ projectId, identities }, null, 2), "utf8");
console.log(`Seeded ${identities.length} emulator identities.`);
