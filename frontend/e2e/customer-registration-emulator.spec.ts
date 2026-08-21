import { randomUUID } from "node:crypto";

import {
  initializeTestEnvironment,
  type RulesTestContext,
  type RulesTestEnvironment,
} from "../../firebase/node_modules/@firebase/rules-unit-testing";
import { expect, test, type Page } from "@playwright/test";

/*
 * This spec has been statically reviewed against the current registration,
 * AppProvider, backend profile-completion contract, and local Emulator
 * boundaries. Runtime Emulator verification has not completed in this
 * environment because Firebase CLI startup reached a network-dependent MOTD
 * and download boundary. No registration E2E pass may be claimed until an
 * explicit opt-in run executes and passes.
 */
const RUN_REGISTRATION_EMULATOR_E2E =
  process.env.RUN_REGISTRATION_EMULATOR_E2E === "1";
const PROJECT_ID = "demo-complaintguard";
const AUTH_ORIGIN = "http://127.0.0.1:9099";
const FIRESTORE_ORIGIN = "http://127.0.0.1:8185";
const LOCAL_ORIGINS = new Set([
  "http://127.0.0.1:3000",
  "http://127.0.0.1:8000",
  AUTH_ORIGIN,
  FIRESTORE_ORIGIN,
]);

type AuthAccount = { localId: string; email?: string };
type AuthSignUpResult = { localId: string };
type EmulatorFirestore = ReturnType<RulesTestContext["firestore"]>;

let rulesEnvironment: RulesTestEnvironment;
const runId = randomUUID().replaceAll("-", "").slice(0, 12);
let identityNumber = 0;

function syntheticEmail(label: string): string {
  identityNumber += 1;
  return `e2e-${runId}-${label}-${identityNumber}@complaintguard.test`;
}

function syntheticPassword(): string {
  return `E2e-${runId}-${randomUUID().slice(0, 10)}!9`;
}

function isAllowedLocalRequest(url: string): boolean {
  try {
    const parsed = new URL(url);
    return LOCAL_ORIGINS.has(`${parsed.protocol}//${parsed.host}`);
  } catch {
    return url === "about:blank" || url.startsWith("data:");
  }
}

async function isolateBrowserTraffic(page: Page): Promise<string[]> {
  const blocked: string[] = [];
  await page.route("**/*", async (route) => {
    if (isAllowedLocalRequest(route.request().url())) {
      await route.continue();
      return;
    }
    blocked.push(route.request().url());
    await route.abort();
  });
  return blocked;
}

async function authAccounts(): Promise<AuthAccount[]> {
  const response = await fetch(
    `${AUTH_ORIGIN}/identitytoolkit.googleapis.com/v1/projects/${PROJECT_ID}/accounts:batchGet?maxResults=1000`,
    { headers: { Authorization: "Bearer owner" } },
  );
  if (!response.ok) throw new Error("auth_emulator_accounts_unavailable");
  const payload = (await response.json()) as { users?: AuthAccount[] };
  return payload.users ?? [];
}

async function createAuthIdentity(email: string, password: string): Promise<string> {
  const response = await fetch(
    `${AUTH_ORIGIN}/identitytoolkit.googleapis.com/v1/accounts:signUp?key=emulator-only`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, returnSecureToken: false }),
    },
  );
  if (!response.ok) throw new Error("auth_emulator_signup_failed");
  return ((await response.json()) as AuthSignUpResult).localId;
}

async function withRulesDisabled<T>(operation: (db: EmulatorFirestore) => Promise<T>): Promise<T> {
  let result: T;
  await rulesEnvironment.withSecurityRulesDisabled(async (context) => {
    result = await operation(context.firestore());
  });
  return result!;
}

async function writeProfile(uid: string, value: Record<string, unknown>): Promise<void> {
  await withRulesDisabled(async (db) => {
    await db.doc(`users/${uid}`).set(value);
  });
}

async function readProfile(uid: string): Promise<Record<string, unknown>> {
  return withRulesDisabled(async (db) => {
    const snapshot = await db.doc(`users/${uid}`).get();
    if (!snapshot.exists) throw new Error("profile_not_created");
    return (snapshot.data() ?? {}) as Record<string, unknown>;
  });
}

function validProfile(email: string, role: string, departmentId: string | null = null) {
  return {
    email,
    displayName: "Synthetic Fixture",
    locale: "en",
    role,
    departmentId,
    active: true,
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  };
}

async function completeForm(page: Page, email: string, displayName: string, locale = "en") {
  const password = syntheticPassword();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Display name").fill(displayName);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel("Confirm password").fill(password);
  if (locale === "my") {
    await page.getByRole("radio", { name: "Myanmar" }).check();
  }
  await page.getByRole("checkbox").check();
}

async function signIn(page: Page, email: string, password: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

test.beforeAll(async () => {
  test.skip(
    !RUN_REGISTRATION_EMULATOR_E2E,
    "Skipped: set RUN_REGISTRATION_EMULATOR_E2E=1 for an intentional local Emulator run.",
  );
  rulesEnvironment = await initializeTestEnvironment({
    projectId: PROJECT_ID,
    firestore: { host: "127.0.0.1", port: 8185 },
  });
});

test.afterAll(async () => {
  if (rulesEnvironment) await rulesEnvironment.cleanup();
});

test("registers one Customer, blocks double submission, and signs in again", async ({ page }) => {
  const blocked = await isolateBrowserTraffic(page);
  const email = syntheticEmail("english");
  const password = syntheticPassword();
  const before = (await authAccounts()).length;
  const completionBodies: Record<string, unknown>[] = [];
  await page.route("**/auth/customer-profile", async (route) => {
    completionBodies.push(route.request().postDataJSON() as Record<string, unknown>);
    await route.continue();
  });

  await page.goto("/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Display name").fill("  Synthetic   English Customer ");
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel("Confirm password").fill(password);
  await page.getByRole("checkbox").check();
  const submit = page.getByRole("button", { name: "Create account" });
  await Promise.all([submit.click(), submit.click()]);
  await expect(page).toHaveURL(/\/dashboard$/u);
  await expect(page.getByRole("heading", { name: "Customer dashboard" })).toBeVisible();

  const after = await authAccounts();
  expect(after).toHaveLength(before + 1);
  const account = after.find((candidate) => candidate.email === email);
  expect(account?.localId).toBeTruthy();
  expect(completionBodies).toHaveLength(1);
  expect(completionBodies[0]).toEqual({
    displayName: "Synthetic English Customer",
    locale: "en",
    termsAccepted: true,
  });
  expect(completionBodies[0]).not.toHaveProperty("password");

  const profile = await readProfile(account!.localId);
  expect(profile).toMatchObject({
    email,
    displayName: "Synthetic English Customer",
    locale: "en",
    role: "customer",
    departmentId: null,
    active: true,
  });
  expect(profile.createdAt).toBeTruthy();
  expect(profile.updatedAt).toBeTruthy();

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/u);
  await signIn(page, email, password);
  await expect(page).toHaveURL(/\/dashboard$/u);
  expect(blocked.every((url) => url.includes("fontshare.com"))).toBe(true);
});

test("blocks invalid registration input before Auth creation", async ({ page }) => {
  const blocked = await isolateBrowserTraffic(page);
  const before = (await authAccounts()).length;
  await page.goto("/register");

  await page.getByLabel("Email").fill("not-an-email");
  await page.getByLabel("Display name").fill("Customer");
  await page.getByLabel("Password", { exact: true }).fill("short");
  await page.getByLabel("Confirm password").fill("different");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.locator('[role="alert"]')).toBeFocused();
  await expect(page.getByText("Enter a valid email address.")).toBeVisible();
  await expect(page.getByText("Choose a password with at least 8 characters, including a letter and a number.")).toBeVisible();
  await expect(page.getByText("Passwords do not match.")).toBeVisible();
  expect(await authAccounts()).toHaveLength(before);

  expect(await page.getByLabel("Password", { exact: true }).getAttribute("type")).toBe("password");
  await page.getByRole("button", { name: "Show password" }).click();
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute("type", "text");

  await page.getByRole("button", { name: "Myanmar" }).click();
  await expect(page.getByRole("heading", { name: /Customer/u })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(blocked.every((url) => url.includes("fontshare.com"))).toBe(true);
});

test("duplicate email is safe", async ({ page }) => {
  const email = syntheticEmail("duplicate");
  const password = syntheticPassword();
  const first = await isolateBrowserTraffic(page);
  await page.goto("/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Display name").fill("Duplicate Source");
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel("Confirm password").fill(password);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/dashboard$/u);
  const beforeDuplicate = await authAccounts();
  const originalCount = beforeDuplicate.length;
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/u);

  await page.goto("/register");
  await completeForm(page, email, "Duplicate Retry");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("An account with this email already exists. Try signing in instead.")).toBeVisible();
  await expect.poll(async () => (await authAccounts()).length).toBe(originalCount);
  expect(first.every((url) => url.includes("fontshare.com"))).toBe(true);
});

test("temporary completion failure retries without a second Auth identity", async ({ page }) => {
  const blocked = await isolateBrowserTraffic(page);
  const email = syntheticEmail("retry");
  const password = syntheticPassword();
  let completionAttempts = 0;
  await page.route("**/auth/customer-profile", async (route) => {
    completionAttempts += 1;
    if (completionAttempts === 1) {
      await route.fulfill({ status: 503, contentType: "application/json", body: '{"error":{"code":"unavailable"}}' });
      return;
    }
    await route.continue();
  });
  const before = (await authAccounts()).length;
  await page.goto("/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Display name").fill("Retry Customer");
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByLabel("Confirm password").fill(password);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("Your account was created, but setup is not complete. Try again to finish it.")).toBeVisible();
  expect(await authAccounts()).toHaveLength(before + 1);
  await page.getByRole("button", { name: "Retry setup" }).click();
  await expect(page).toHaveURL(/\/dashboard$/u);
  expect(completionAttempts).toBe(2);
  expect(await authAccounts()).toHaveLength(before + 1);
  expect(blocked.every((url) => url.includes("fontshare.com"))).toBe(true);
});

test("later login with a missing profile opens recovery without creating Auth", async ({ page }) => {
  const blocked = await isolateBrowserTraffic(page);
  const email = syntheticEmail("missing");
  const password = syntheticPassword();
  await createAuthIdentity(email, password);
  const before = await authAccounts();
  await signIn(page, email, password);
  await expect(page.getByText("Your account was created, but setup is not complete. Try again to finish it.")).toBeVisible();
  await page.getByRole("link", { name: "Finish setup" }).click();
  await page.getByLabel("Display name").fill("Recovered Customer");
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Finish setup" }).click();
  await expect(page).toHaveURL(/\/dashboard$/u);
  expect(await authAccounts()).toHaveLength(before.length);
  expect(blocked.every((url) => url.includes("fontshare.com"))).toBe(true);
});

test("privileged, inactive, and malformed profiles cannot use public recovery", async ({ browser }) => {
  const cases = [
    ["staff", validProfile(syntheticEmail("staff"), "staff", "card_atm")],
    ["manager", validProfile(syntheticEmail("manager"), "manager")],
    ["admin", validProfile(syntheticEmail("admin"), "admin")],
    ["inactive", { ...validProfile(syntheticEmail("inactive"), "customer"), active: false }],
    ["malformed", { email: syntheticEmail("malformed"), displayName: "Malformed", role: "customer" }],
  ] as const;

  for (const [label, profile] of cases) {
    const context = await browser.newContext();
    const page = await context.newPage();
    const blocked = await isolateBrowserTraffic(page);
    const email = profile.email;
    const password = syntheticPassword();
    const uid = await createAuthIdentity(email, password);
    await writeProfile(uid, profile);
    const completionRequests: string[] = [];
    await page.route("**/auth/customer-profile", async (route) => {
      completionRequests.push(route.request().url());
      await route.continue();
    });
    await signIn(page, email, password);
    if (label === "staff") {
      await expect(page.getByRole("heading", { name: "Department staff dashboard" })).toBeVisible();
    } else if (label === "manager") {
      await expect(page.getByRole("heading", { name: "Manager dashboard" })).toBeVisible();
    } else if (label === "admin") {
      await expect(page.getByRole("heading", { name: "Administration dashboard" })).toBeVisible();
    } else {
      await page.goto("/register");
      await expect(page.getByText("We could not complete account setup. Please contact support for help.")).toBeVisible();
    }
    expect(completionRequests).toHaveLength(0);
    expect(blocked.every((url) => url.includes("fontshare.com"))).toBe(true);
    await context.close();
  }
});

test("direct client profile mutations remain denied", async () => {
  const email = syntheticEmail("rules");
  const uid = await createAuthIdentity(email, syntheticPassword());
  const db = rulesEnvironment.authenticatedContext(uid).firestore();
  const profile = db.doc(`users/${uid}`);
  await expect(profile.set({ role: "customer" })).rejects.toThrow();
  await expect(profile.update({ role: "admin" })).rejects.toThrow();
  await expect(profile.delete()).rejects.toThrow();
});
