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

async function signIn(page: Page, identity: Identity, dashboard: string | RegExp) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(identity.email);
  await page.getByLabel("Password", { exact: true }).fill(identity.password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/u);
  await expect(page.getByRole("heading", { name: dashboard })).toBeVisible();
}

async function signOut(page: Page) {
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/u);
}

async function submitAndReplay(page: Page, complaint: string) {
  let requestBody = "";
  let authorization = "";
  let submissionPostCount = 0;
  await page.route("**/tickets", async (route) => {
    if (route.request().method() === "POST") {
      submissionPostCount += 1;
      requestBody = route.request().postData() || "";
      authorization = (await route.request().allHeaders()).authorization || "";
    }
    await route.continue();
  });
  await page.getByRole("button", { name: "New Complaint", exact: true }).click();
  const complaintModal = page.getByRole("dialog", { name: "Submit a complaint", exact: true });
  await expect(complaintModal).toBeVisible();
  await complaintModal.getByLabel("Complaint", { exact: true }).fill(complaint);
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
  expect(submissionPostCount).toBe(1);
  const responsePayload = await submissionResponse.json();
  expect(responsePayload).toEqual({
    complaintId: expect.stringMatching(/^ticket_[a-f0-9]{32}$/u),
    status: "submitted",
  });
  const ticketId = responsePayload.complaintId as string;
  await page.unroute("**/tickets");
  const failure = page.getByRole("alert").filter({ hasText: /complaint/u });
  await expect(complaintModal).toBeHidden();
  await expect(failure).toHaveCount(0);
  const historyTicket = page.getByRole("button", { name: new RegExp(ticketId, "u") });
  await expect(historyTicket).toHaveCount(1);
  await expect(historyTicket).toHaveAttribute("aria-pressed", "true");
  const customerDetail = page.getByRole("article", { name: "Complaint details", exact: true });
  await expect(customerDetail.getByText(new RegExp(`^Ticket ID: ${ticketId}$`, "u"))).toBeVisible();
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

test("Day 17 routing state and role isolation use real emulator identities", async ({ page }) => {
  const users = await identities();

  await signIn(page, users.customer, /^Welcome, .+$/u);
  const highId = await submitAndReplay(
    page,
    "My credit report contains accounts caused by identity theft and fraud.",
  );
  expect(highId).not.toBe("");
  await refreshAndOpen(page, highId);
  const customerDetail = page.getByRole("article", { name: "Complaint details", exact: true });
  await expect(customerDetail).toBeVisible();
  await expect(customerDetail.getByText("Triaged", { exact: true })).toBeVisible();
  await expect(customerDetail.getByText("Predicted department", { exact: true })).toHaveCount(0);
  await expect(customerDetail.getByText("Model routing evidence", { exact: true })).toHaveCount(0);
  await expect(customerDetail.getByText("Model confidence", { exact: true })).toHaveCount(0);
  await expect(customerDetail.getByText("Routing state", { exact: true })).toHaveCount(0);
  await signOut(page);

  await signIn(page, users.staffCard, "Staff workspace");
  await expect(page.getByText(highId)).toHaveCount(0);
  await signOut(page);

  await signIn(page, users.staffFraud, "Staff workspace");
  await page.getByRole("button", { name: new RegExp(highId, "u") }).click();
  await page.getByRole("button", { name: "Begin work" }).click();
  await expect(page.getByRole("button", { name: "Await customer" })).toBeVisible();
  await page.getByRole("tab", { name: "Messages", exact: true }).click();
  const staffMessages = page.getByRole("tabpanel", { name: "Messages", exact: true });
  await expect(staffMessages).toBeVisible();
  await staffMessages.getByLabel("Participant reply", { exact: true }).fill("Complete staff E2E reply.");
  await page.getByRole("button", { name: "Send reply" }).click();
  await expect(page.getByText("Complete staff E2E reply.")).toBeVisible();
  await page.getByRole("tab", { name: "Overview", exact: true }).click();
  const staffOverview = page.getByRole("tabpanel", { name: "Overview", exact: true });
  await expect(staffOverview).toBeVisible();
  await page.getByRole("button", { name: "Await customer" }).click();
  await expect(page.getByRole("button", { name: "Resume work" })).toBeVisible();
  await signOut(page);

  await signIn(page, users.customer, /^Welcome, .+$/u);
  await refreshAndOpen(page, highId);
  const customerDetailAfterStaffReply = page.getByRole("article", { name: "Complaint details", exact: true });
  await expect(customerDetailAfterStaffReply.getByText("Awaiting customer", { exact: true })).toBeVisible();
  await expect(customerDetailAfterStaffReply.getByText("The support team needs more information from you. Reply in the message area to continue.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Messages", exact: true }).click();
  const customerMessages = page.getByRole("dialog", { name: "Messages", exact: true });
  await expect(customerMessages).toBeVisible();
  await expect(customerMessages.getByText("Complete staff E2E reply.", { exact: true })).toBeVisible();
  await customerMessages.getByLabel("Send message to department staff", { exact: true }).fill("Complete customer E2E reply.");
  await customerMessages.getByRole("button", { name: "Send message", exact: true }).click();
  await expect(customerMessages.getByText("Complete customer E2E reply.", { exact: true })).toBeVisible();
  await customerMessages.getByRole("button", { name: "Close messages", exact: true }).click();
  await expect(customerMessages).toBeHidden();
  const lowId = await submitAndReplay(page, "I cannot understand this fee.");
  await refreshAndOpen(page, lowId);
  const lowConfidenceCustomerDetail = page.getByRole("article", { name: "Complaint details", exact: true });
  await expect(lowConfidenceCustomerDetail.getByText("Submitted", { exact: true })).toBeVisible();
  await expect(lowConfidenceCustomerDetail.getByText("Your complaint was received. The support team will review it. Reply only if we ask for more information.", { exact: true })).toBeVisible();
  await expect(lowConfidenceCustomerDetail.getByText("Manual review", { exact: true })).toHaveCount(0);
  await expect(lowConfidenceCustomerDetail.getByText("Prediction confidence", { exact: true })).toHaveCount(0);
  await expect(lowConfidenceCustomerDetail.getByText("Model routing evidence", { exact: true })).toHaveCount(0);
  await expect(lowConfidenceCustomerDetail.getByText("Routing source", { exact: true })).toHaveCount(0);
  await signOut(page);

  await signIn(page, users.staffCard, "Staff workspace");
  await expect(page.getByText(lowId)).toHaveCount(0);
  await signOut(page);

  await signIn(page, users.manager, "Manager workspace");
  await page.getByRole("button", { name: "Low-Confidence Prediction Review", exact: true }).click();
  await expect(page.getByRole("table")).toBeVisible();
  const row = page.getByRole("row").filter({ hasText: lowId });
  await expect(row).toBeVisible();
  await row.getByRole("button", { name: "Reassign Department", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "Manager Department Override" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Confirm Override" })).toBeDisabled();
  await page.getByLabel("Select Target Department", { exact: true }).selectOption("card_atm");
  await page.getByLabel("Reason for Department Reassignment", { exact: true }).fill("Approved in emulator browser review");
  const overrideResponsePromise = page.waitForResponse(
    (response) => response.url().includes(`/manager/tickets/${lowId}/override`) && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Confirm Override" }).click();
  const overrideResponse = await overrideResponsePromise;
  expect(overrideResponse.status()).toBe(200);
  await expect(overrideResponse.json()).resolves.toEqual({
    ticketId: lowId,
    departmentId: "card_atm",
    routingSource: "manager_override",
    updatedAt: expect.any(String),
  });
  await expect(row).toBeVisible();
  await signOut(page);

  await signIn(page, users.staffCard, "Staff workspace");
  await expect(page.getByRole("button", { name: new RegExp(lowId, "u") })).toHaveCount(1);
  await signOut(page);

  await signIn(page, users.staffFraud, "Staff workspace");
  await page.getByRole("button", { name: new RegExp(highId, "u") }).click();
  await page.getByRole("tab", { name: "Messages", exact: true }).click();
  const staffMessagesAfterCustomerReply = page.getByRole("tabpanel", { name: "Messages", exact: true });
  await expect(staffMessagesAfterCustomerReply.getByText("Complete customer E2E reply.", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Overview", exact: true }).click();
  await expect(page.getByRole("tabpanel", { name: "Overview", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Resume work" }).click();
  await page.getByLabel("Resolution summary").fill("Synthetic resolution completed.");
  await page.getByRole("button", { name: "Resolve complaint" }).click();
  await expect(page.getByText("Synthetic resolution completed.")).toBeVisible();
  await signOut(page);

  await signIn(page, users.customer, /^Welcome, .+$/u);
  await refreshAndOpen(page, highId);
  const resolvedCustomerDetail = page.getByRole("article", { name: "Complaint details", exact: true });
  const resolvedStatus = resolvedCustomerDetail.getByRole("region", { name: "Current status", exact: true });
  await expect(resolvedStatus.getByText("Resolved", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "4 out of 5 stars" }).click();
  await page.getByRole("button", { name: "Submit feedback" }).click();
  await expect(page.getByText("Thank you for your rating and feedback.")).toBeVisible();
});

test("additional emulator customers submit and see only their own synthetic tickets", async ({ page }) => {
  const users = await identities();
  const priorTicketIds: string[] = [];

  for (const key of ["customerTwo", "customerThree", "customerFour"]) {
    await signIn(page, users[key], /^Welcome, .+$/u);
    for (const priorTicketId of priorTicketIds) {
      await expect(page.getByText(priorTicketId)).toHaveCount(0);
    }
    const complaint = `Synthetic demo fee question for ${key}.`;
    const ticketId = await submitAndReplay(page, complaint);
    await refreshAndOpen(page, ticketId);
    const customerDetail = page.getByRole("article", { name: "Complaint details", exact: true });
    await expect(customerDetail.getByText(complaint, { exact: true })).toBeVisible();
    priorTicketIds.push(ticketId);
    await signOut(page);
  }
});

test("customer, staff, and manager dashboards remain bilingual and viewport-contained on mobile", async ({ page }) => {
  const users = await identities();
  await page.setViewportSize({ width: 390, height: 844 });

  for (const [identity, dashboard, myanmarDashboard] of [
    [users.customer, /^Welcome, .+$/u, /^ကြိုဆိုပါတယ်, .+$/u],
    [users.staffCard, "Staff workspace", "ဝန်ထမ်းလုပ်ငန်းခွင်"],
    [users.manager, "Manager workspace", "မန်နေဂျာလုပ်ငန်းခွင်"],
  ] as const) {
    await signIn(page, identity, dashboard);
    const myanmarButton = page.getByRole("button", { name: "Myanmar", exact: true });
    await myanmarButton.click();
    const myanmarLanguageGroup = page.getByRole("group", { name: "ဘာသာစကား", exact: true });
    const selectedMyanmarButton = myanmarLanguageGroup.getByRole("button", { name: "မြန်မာ", exact: true, pressed: true });
    await expect(selectedMyanmarButton).toHaveCount(1);
    await expect(page.getByRole("heading", { name: myanmarDashboard, exact: true })).toBeVisible();
    await expect
      .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
      .toBe(true);
    await page.getByRole("button", { name: "English", exact: true }).click();
    await signOut(page);
  }

  await page.goto("/login");
  await page.keyboard.press("Tab");
  const focusedOutline = await page.evaluate(() =>
    getComputedStyle(document.activeElement as Element).outlineStyle,
  );
  expect(focusedOutline).not.toBe("none");
});
