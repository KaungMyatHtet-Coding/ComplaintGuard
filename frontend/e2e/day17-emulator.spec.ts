import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";

type Identity = { key: string; email: string; password: string };

async function identities(): Promise<Record<string, Identity>> {
  const value = JSON.parse(
    await readFile(
      process.env.COMPLAINTGUARD_EMULATOR_IDENTITIES ||
        resolve("..", "firebase", ".firebase", "seeded-identities.json"),
      "utf8",
    ),
  );
  return Object.fromEntries(value.identities.map((item: Identity) => [item.key, item]));
}

async function signIn(page: Page, identity: Identity, dashboard: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(identity.email);
  await page.getByLabel("Password").fill(identity.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: dashboard })).toBeVisible();
}

async function signOut(page: Page) {
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/u);
}

async function submitAndReplay(page: Page, complaint: string) {
  let requestBody = "";
  let authorization = "";
  await page.route("**/tickets", async (route) => {
    if (route.request().method() === "POST") {
      requestBody = route.request().postData() || "";
      authorization = (await route.request().allHeaders()).authorization || "";
    }
    await route.continue();
  });
  await page.locator("#complaint-text").fill(complaint);
  const responsePromise = page.waitForResponse(
    (response) =>
      response.url() === "http://127.0.0.1:8000/tickets" &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Submit complaint" }).click();
  const submissionResponse = await responsePromise;
  if (!submissionResponse.ok()) {
    const payload = await submissionResponse.json();
    throw new Error(
      `submission_backend_error:${submissionResponse.status()}:${payload?.error?.code ?? "unknown"}`,
    );
  }
  const success = page.getByText("Complaint submitted successfully.");
  const failure = page.locator('[role="alert"]').filter({ hasText: /complaint/u });
  await expect(success.or(failure)).toBeVisible();
  if (await failure.isVisible()) {
    throw new Error(`submission_ui_error:${await failure.textContent()}`);
  }
  const reference = await page.getByText(/Reference ID:/u).textContent();
  const ticketId = reference?.split(":").at(-1)?.trim() || "";
  await page.unroute("**/tickets");
  const replayId = await page.evaluate(
    async ({ body, token }) => {
      const response = await fetch("http://127.0.0.1:8000/tickets", {
        method: "POST",
        headers: { Authorization: token, "Content-Type": "application/json" },
        body,
      });
      if (!response.ok) throw new Error(`retry_failed:${response.status}`);
      return (await response.json()).complaintId as string;
    },
    { body: requestBody, token: authorization },
  );
  expect(replayId).toBe(ticketId);
  return ticketId;
}

async function refreshAndOpen(page: Page, ticketId: string) {
  await page.getByRole("button", { name: "Refresh" }).click();
  await page.getByRole("button", { name: new RegExp(ticketId, "u") }).click();
}

test("Day 17 high/low routing and role isolation use real emulator identities", async ({ page }) => {
  const users = await identities();

  await signIn(page, users.customer, "Customer dashboard");
  const highId = await submitAndReplay(
    page,
    "My credit report contains accounts caused by identity theft and fraud.",
  );
  expect(highId).not.toBe("");
  await refreshAndOpen(page, highId);
  const predictedDepartment = page
    .getByText("Predicted department", { exact: true })
    .locator("..")
    .getByRole("definition");
  await expect(predictedDepartment).toHaveText("Fraud & Security");
  await expect(page.getByText("Model routing evidence", { exact: true })).toBeVisible();
  await signOut(page);

  await signIn(page, users.staffCard, "Department staff dashboard");
  await expect(page.getByText(highId)).toHaveCount(0);
  await signOut(page);

  await signIn(page, users.staffFraud, "Department staff dashboard");
  await page.getByRole("button", { name: new RegExp(highId, "u") }).click();
  await page.getByRole("button", { name: "Begin work" }).click();
  await expect(page.getByRole("button", { name: "Await customer" })).toBeVisible();
  await page.getByLabel("Participant reply").fill("Complete staff E2E reply.");
  await page.getByRole("button", { name: "Send reply" }).click();
  await expect(page.getByText("Complete staff E2E reply.")).toBeVisible();
  await page.getByRole("button", { name: "Await customer" }).click();
  await expect(page.getByRole("button", { name: "Resume work" })).toBeVisible();
  await signOut(page);

  await signIn(page, users.customer, "Customer dashboard");
  await refreshAndOpen(page, highId);
  await expect(page.getByText("Complete staff E2E reply.")).toBeVisible();
  await expect(page.getByText("Waiting for your reply", { exact: true })).toBeVisible();
  await page
    .getByPlaceholder("Send message to department staff")
    .fill("Complete customer E2E reply.");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(page.getByText("Complete customer E2E reply.")).toBeVisible();
  const lowId = await submitAndReplay(page, "I cannot understand this fee.");
  await refreshAndOpen(page, lowId);
  await expect(page.getByText("Manual review", { exact: true })).toBeVisible();
  await signOut(page);

  await signIn(page, users.staffCard, "Department staff dashboard");
  await expect(page.getByText(lowId)).toHaveCount(0);
  await signOut(page);

  await signIn(page, users.manager, "Manager dashboard");
  const row = page.getByRole("row").filter({ hasText: lowId });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "Reassign" }).click();
  await expect(page.getByRole("dialog", { name: "Manager Department Override" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Confirm Override" })).toBeDisabled();
  await page.locator("#dept-select").selectOption("card_atm");
  await page.locator("#override-reason").fill("Approved in emulator browser review");
  await page.getByRole("button", { name: "Confirm Override" }).click();
  await expect(row).toHaveCount(0);
  await signOut(page);

  await signIn(page, users.staffCard, "Department staff dashboard");
  await expect(page.getByText(lowId)).toBeVisible();
  await signOut(page);

  await signIn(page, users.staffFraud, "Department staff dashboard");
  await page.getByRole("button", { name: new RegExp(highId, "u") }).click();
  await expect(page.getByText("Complete customer E2E reply.")).toBeVisible();
  await page.getByRole("button", { name: "Resume work" }).click();
  await page.getByLabel("Resolution summary").fill("Synthetic resolution completed.");
  await page.getByRole("button", { name: "Resolve complaint" }).click();
  await expect(page.getByText("Synthetic resolution completed.")).toBeVisible();
  await signOut(page);

  await signIn(page, users.customer, "Customer dashboard");
  await refreshAndOpen(page, highId);
  await expect(page.getByText("Resolved", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "4 out of 5 stars" }).click();
  await page.getByRole("button", { name: "Submit feedback" }).click();
  await expect(page.getByText("Thank you for your rating and feedback.")).toBeVisible();
});

test("additional emulator customers submit and see only their own synthetic tickets", async ({ page }) => {
  const users = await identities();
  const priorTicketIds: string[] = [];

  for (const key of ["customerTwo", "customerThree", "customerFour"]) {
    await signIn(page, users[key], "Customer dashboard");
    for (const priorTicketId of priorTicketIds) {
      await expect(page.getByText(priorTicketId)).toHaveCount(0);
    }
    const complaint = `Synthetic demo fee question for ${key}.`;
    const ticketId = await submitAndReplay(page, complaint);
    await refreshAndOpen(page, ticketId);
    await expect(page.getByText(complaint, { exact: true }).last()).toBeVisible();
    priorTicketIds.push(ticketId);
    await signOut(page);
  }
});

test("customer, staff, and manager dashboards remain bilingual and viewport-contained on mobile", async ({ page }) => {
  const users = await identities();
  await page.setViewportSize({ width: 390, height: 844 });

  for (const [identity, dashboard] of [
    [users.customer, "Customer dashboard"],
    [users.staffCard, "Department staff dashboard"],
    [users.manager, "Manager dashboard"],
  ] as const) {
    await signIn(page, identity, dashboard);
    await page.locator(".language-switcher button").nth(1).click();
    await expect(page.locator(".language-switcher button").nth(1)).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
      .toBe(true);
    await page.locator(".language-switcher button").first().click();
    await signOut(page);
  }

  await page.goto("/login");
  await page.keyboard.press("Tab");
  const focusedOutline = await page.evaluate(() =>
    getComputedStyle(document.activeElement as Element).outlineStyle,
  );
  expect(focusedOutline).not.toBe("none");
});
