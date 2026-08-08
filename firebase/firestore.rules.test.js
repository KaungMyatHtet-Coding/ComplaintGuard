import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  assertFails,
  assertSucceeds,
  initializeTestEnvironment,
} from "@firebase/rules-unit-testing";
import { doc, getDoc, setDoc } from "firebase/firestore";
import { afterAll, beforeAll, beforeEach, describe, it } from "vitest";

const projectId = "demo-complaintguard";
let testEnvironment;

beforeAll(async () => {
  testEnvironment = await initializeTestEnvironment({
    projectId,
    firestore: {
      rules: readFileSync(resolve("firestore.rules"), "utf8"),
    },
  });
});

beforeEach(async () => {
  await testEnvironment.clearFirestore();
  await testEnvironment.withSecurityRulesDisabled(async (context) => {
    const db = context.firestore();
    await setDoc(doc(db, "users/customer-a"), { role: "customer", active: true });
    await setDoc(doc(db, "users/customer-b"), { role: "customer", active: true });
    await setDoc(doc(db, "users/staff-card"), {
      role: "staff",
      active: true,
      departmentId: "card_atm",
    });
    await setDoc(doc(db, "users/staff-loan"), {
      role: "staff",
      active: true,
      departmentId: "loan_credit",
    });
    await setDoc(doc(db, "users/manager-a"), { role: "manager", active: true });
    await setDoc(doc(db, "tickets/card-ticket"), {
      customerId: "customer-a",
      departmentId: "card_atm",
    });
    await setDoc(doc(db, "tickets/pending-ticket"), {
      customerId: "customer-b",
      departmentId: null,
    });
    await setDoc(doc(db, "tickets/card-ticket/messages/message-a"), {
      authorId: "customer-a",
      body: "Synthetic message",
    });
    await setDoc(doc(db, "tickets/card-ticket/events/event-a"), {
      actorId: "staff-card",
      type: "status_changed",
    });
  });
});

afterAll(async () => {
  await testEnvironment.cleanup();
});

describe("ComplaintGuard Firestore rules", () => {
  it("limits customers to their own tickets", async () => {
    const db = testEnvironment.authenticatedContext("customer-a").firestore();
    await assertSucceeds(getDoc(doc(db, "tickets/card-ticket")));
    await assertFails(getDoc(doc(db, "tickets/pending-ticket")));
  });

  it("requires exact staff department and denies null-department tickets", async () => {
    const cardDb = testEnvironment.authenticatedContext("staff-card").firestore();
    const loanDb = testEnvironment.authenticatedContext("staff-loan").firestore();
    await assertSucceeds(getDoc(doc(cardDb, "tickets/card-ticket")));
    await assertFails(getDoc(doc(loanDb, "tickets/card-ticket")));
    await assertFails(getDoc(doc(cardDb, "tickets/pending-ticket")));
  });

  it("allows active managers to read tickets", async () => {
    const db = testEnvironment.authenticatedContext("manager-a").firestore();
    await assertSucceeds(getDoc(doc(db, "tickets/card-ticket")));
    await assertSucceeds(getDoc(doc(db, "tickets/pending-ticket")));
  });

  it("denies direct client ticket, message, and event writes", async () => {
    const customerDb = testEnvironment.authenticatedContext("customer-a").firestore();
    const staffDb = testEnvironment.authenticatedContext("staff-card").firestore();
    await assertFails(setDoc(doc(customerDb, "tickets/new-ticket"), { customerId: "customer-a" }));
    await assertFails(setDoc(doc(customerDb, "tickets/card-ticket/messages/new-message"), { body: "x" }));
    await assertFails(setDoc(doc(staffDb, "tickets/card-ticket/events/new-event"), { type: "x" }));
  });
});
