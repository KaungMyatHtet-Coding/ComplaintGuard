import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { assertFails } from "@firebase/rules-unit-testing";
import { deleteApp, initializeApp } from "firebase/app";
import {
  connectAuthEmulator,
  getAuth,
  signInWithEmailAndPassword,
  signOut,
} from "firebase/auth";
import { connectFirestoreEmulator, doc, getDoc, getFirestore } from "firebase/firestore";
import { describe, expect, it } from "vitest";

const expectedStaffDepartments = {
  staffFraud: "fraud_security",
  staffCard: "card_atm",
  staffTransfer: "transfer_payment",
  staffAccount: "account_support",
  staffLoan: "loan_credit",
  staffGeneral: "general_support",
};

describe("ComplaintGuard Auth Emulator identities", () => {
  it("authenticates every seeded role and reads only its trusted profile", async () => {
    const seed = JSON.parse(
      await readFile(resolve(".firebase", "seeded-identities.json"), "utf8"),
    );
    expect(seed.identities).toHaveLength(11);
    expect(new Set(seed.identities.map((identity) => identity.uid)).size).toBe(11);
    expect(new Set(seed.identities.map((identity) => identity.email)).size).toBe(11);
    const accountsResponse = await fetch(
      `http://127.0.0.1:9099/identitytoolkit.googleapis.com/v1/projects/${seed.projectId}/accounts:batchGet?maxResults=1000`,
      { headers: { Authorization: "Bearer owner" } },
    );
    expect(accountsResponse.ok).toBe(true);
    const authEmails = new Set(
      ((await accountsResponse.json()).users ?? []).map((user) => user.email),
    );
    expect(authEmails).toEqual(new Set(seed.identities.map((identity) => identity.email)));
    expect(
      Object.fromEntries(
        seed.identities
          .filter((identity) => identity.role === "staff")
          .map((identity) => [identity.key, identity.departmentId]),
      ),
    ).toEqual(expectedStaffDepartments);

    for (const identity of seed.identities) {
      const app = initializeApp(
        { apiKey: "emulator-only", projectId: seed.projectId },
        `auth-test-${identity.key}`,
      );
      const auth = getAuth(app);
      connectAuthEmulator(auth, "http://127.0.0.1:9099", { disableWarnings: true });
      const db = getFirestore(app);
      connectFirestoreEmulator(db, "127.0.0.1", 8185);
      const credential = await signInWithEmailAndPassword(
        auth,
        identity.email,
        identity.password,
      );
      expect(credential.user.uid).toBe(identity.uid);
      expect(credential.user.emailVerified).toBe(false);
      const profile = await getDoc(doc(db, "users", identity.uid));
      expect(profile.exists()).toBe(true);
      expect(profile.data().role).toBe(identity.role);
      expect(profile.data().active).toBe(true);
      expect(profile.data().departmentId).toBe(identity.departmentId ?? null);
      expect(profile.data().email).toBe(identity.email);
      expect(profile.data().locale).toBe(identity.locale);
      expect(profile.data().createdAt).toBeTruthy();
      expect(profile.data().updatedAt).toBeTruthy();
      const other = seed.identities.find((candidate) => candidate.uid !== identity.uid);
      await assertFails(getDoc(doc(db, "users", other.uid)));
      await signOut(auth);
      expect(auth.currentUser).toBeNull();
      await deleteApp(app);
    }

    const customers = seed.identities.filter((identity) => identity.role === "customer");
    const manager = seed.identities.find((identity) => identity.key === "manager");
    expect(customers).toHaveLength(4);
    expect(customers.every((customer) => !("departmentId" in customer))).toBe(true);
    expect(manager).toMatchObject({ role: "manager" });
    expect(manager).not.toHaveProperty("departmentId");
  });
});
