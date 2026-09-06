import { readFile } from "node:fs/promises";
import { describe, expect, it } from "vitest";
import { initializeTestEnvironment, assertFails } from "@firebase/rules-unit-testing";
import { doc, getDoc, setDoc } from "firebase/firestore";

const projectId = `complaintguard-v2-foundation-${process.pid}`;
let testEnv;

describe("V2 foundation Firestore boundary", () => {
  it("denies direct browser access to privileged V2 collections", async () => {
    testEnv ??= await initializeTestEnvironment({ projectId, firestore: { rules: await readFile(new URL("./firestore.rules", import.meta.url), "utf8") } });
    const db = testEnv.authenticatedContext("customer-1", { email: "customer@example.test" }).firestore();
    await assertFails(getDoc(doc(db, "staffProfiles/staff-1")));
    await assertFails(setDoc(doc(db, "staffProfiles/staff-1"), { staffId: "staff-1" }));
    await assertFails(getDoc(doc(db, "staffIdentities/identity-1")));
    await assertFails(getDoc(doc(db, "auditLogs/audit-1")));
    await assertFails(getDoc(doc(db, "departments/general_complaints/queueState/current")));
  });
});
