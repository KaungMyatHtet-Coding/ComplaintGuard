import { randomBytes } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  assertFails,
  assertSucceeds,
  initializeTestEnvironment,
} from "@firebase/rules-unit-testing";
import { deleteDoc, doc, getDoc, setDoc } from "firebase/firestore";
import { afterAll, beforeAll, beforeEach, describe, it } from "vitest";

const projectId = "demo-complaintguard";
const fixturePrefix = `rules-fixture-v1-${randomBytes(8).toString("hex")}`;
const staffDepartments = [
  { uid: `${fixturePrefix}-staff-fraud`, departmentId: "fraud_security" },
  { uid: `${fixturePrefix}-staff-card`, departmentId: "card_atm" },
  { uid: `${fixturePrefix}-staff-transfer`, departmentId: "transfer_payment" },
  { uid: `${fixturePrefix}-staff-account`, departmentId: "account_support" },
  { uid: `${fixturePrefix}-staff-loan`, departmentId: "loan_credit" },
  { uid: `${fixturePrefix}-staff-general`, departmentId: "general_support" },
];
let testEnvironment;
const ownedPaths = new Set();

async function writeOwned(context, path, data) {
  ownedPaths.add(path);
  await setDoc(doc(context.firestore(), path), data);
}

async function deleteOwnedDocuments() {
  if (!testEnvironment || ownedPaths.size === 0) return;
  const paths = [...ownedPaths].reverse();
  let results;
  await testEnvironment.withSecurityRulesDisabled(async (context) => {
    results = await Promise.allSettled(
      paths.map((path) => deleteDoc(doc(context.firestore(), path))),
    );
  });
  const failures = results.filter((result) => result.status === "rejected");
  if (failures.length > 0) {
    throw new Error(`rules_fixture_cleanup_failed:${failures.length}`);
  }
  ownedPaths.clear();
}

beforeAll(async () => {
  testEnvironment = await initializeTestEnvironment({
    projectId,
    firestore: {
      rules: readFileSync(resolve("firestore.rules"), "utf8"),
    },
  });
});

beforeEach(async () => {
  await deleteOwnedDocuments();
  await testEnvironment.withSecurityRulesDisabled(async (context) => {
    await writeOwned(context, `users/${fixturePrefix}-customer-a`, { role: "customer", active: true });
    await writeOwned(context, `users/${fixturePrefix}-customer-b`, { role: "customer", active: true });
    for (const staff of staffDepartments) {
      await writeOwned(context, `users/${staff.uid}`, {
        role: "staff",
        active: true,
        departmentId: staff.departmentId,
      });
      await writeOwned(context, `tickets/${fixturePrefix}-${staff.departmentId}-ticket`, {
        customerId: `${fixturePrefix}-customer-a`,
        departmentId: staff.departmentId,
      });
    }
    await writeOwned(context, `users/${fixturePrefix}-manager-a`, { role: "manager", active: true });
    await writeOwned(context, `tickets/${fixturePrefix}-card-ticket`, {
      customerId: `${fixturePrefix}-customer-a`,
      departmentId: "card_atm",
    });
    await writeOwned(context, `tickets/${fixturePrefix}-pending-ticket`, {
      customerId: `${fixturePrefix}-customer-b`,
      departmentId: null,
    });
    await writeOwned(context, `tickets/${fixturePrefix}-card-ticket/messages/message-a`, {
      authorId: `${fixturePrefix}-customer-a`,
      body: "Synthetic message",
    });
    await writeOwned(context, `tickets/${fixturePrefix}-card-ticket/events/event-a`, {
      actorId: `${fixturePrefix}-staff-card`,
      type: "status_changed",
    });
  });
});

afterAll(async () => {
  try {
    await deleteOwnedDocuments();
  } finally {
    await testEnvironment.cleanup();
  }
});

describe("ComplaintGuard Firestore rules", () => {
  it("denies raw ticket reads to customers and cross-customer access", async () => {
    const db = testEnvironment.authenticatedContext(`${fixturePrefix}-customer-a`).firestore();
    await assertFails(getDoc(doc(db, `tickets/${fixturePrefix}-card-ticket`)));
    await assertFails(getDoc(doc(db, `tickets/${fixturePrefix}-pending-ticket`)));
  });

  it("denies raw ticket reads to staff regardless of department", async () => {
    for (const [index, staff] of staffDepartments.entries()) {
      const db = testEnvironment.authenticatedContext(staff.uid).firestore();
      const otherDepartment = staffDepartments[(index + 1) % staffDepartments.length];
      await assertFails(
        getDoc(doc(db, `tickets/${fixturePrefix}-${otherDepartment.departmentId}-ticket`)),
      );
      await assertFails(getDoc(doc(db, `tickets/${fixturePrefix}-${staff.departmentId}-ticket`)));
      await assertFails(getDoc(doc(db, `tickets/${fixturePrefix}-pending-ticket`)));
    }
  });

  it("denies raw ticket reads to managers", async () => {
    const db = testEnvironment.authenticatedContext(`${fixturePrefix}-manager-a`).firestore();
    await assertFails(getDoc(doc(db, `tickets/${fixturePrefix}-card-ticket`)));
    await assertFails(getDoc(doc(db, `tickets/${fixturePrefix}-pending-ticket`)));
  });

  it("denies raw ticket, message, and event reads to customers", async () => {
    const db = testEnvironment.authenticatedContext(`${fixturePrefix}-customer-a`).firestore();
    await assertFails(getDoc(doc(db, `tickets/${fixturePrefix}-card-ticket/messages/message-a`)));
    await assertFails(getDoc(doc(db, `tickets/${fixturePrefix}-card-ticket/events/event-a`)));
  });

  it("denies direct client ticket, message, and event writes", async () => {
    const customerDb = testEnvironment.authenticatedContext(`${fixturePrefix}-customer-a`).firestore();
    const staffDb = testEnvironment.authenticatedContext(`${fixturePrefix}-staff-card`).firestore();
    await assertFails(setDoc(doc(customerDb, `tickets/${fixturePrefix}-new-ticket`), { customerId: `${fixturePrefix}-customer-a` }));
    await assertFails(setDoc(doc(customerDb, `tickets/${fixturePrefix}-card-ticket/messages/new-message`), { body: "x" }));
    await assertFails(setDoc(doc(staffDb, `tickets/${fixturePrefix}-card-ticket/events/new-event`), { type: "x" }));
  });
});
