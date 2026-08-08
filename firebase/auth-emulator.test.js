import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

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
    expect(seed.identities).toHaveLength(8);
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
      const profile = await getDoc(doc(db, "users", identity.uid));
      expect(profile.exists()).toBe(true);
      expect(profile.data().role).toBe(identity.role);
      expect(profile.data().active).toBe(true);
      expect(profile.data().departmentId).toBe(identity.departmentId ?? null);
      await signOut(auth);
      expect(auth.currentUser).toBeNull();
      await deleteApp(app);
    }

    const customer = seed.identities.find((identity) => identity.key === "customer");
    const manager = seed.identities.find((identity) => identity.key === "manager");
    expect(customer).toMatchObject({ role: "customer" });
    expect(customer).not.toHaveProperty("departmentId");
    expect(manager).toMatchObject({ role: "manager" });
    expect(manager).not.toHaveProperty("departmentId");
  });
});
