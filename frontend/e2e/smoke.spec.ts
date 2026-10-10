import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { apac, jsonl, receipt } from "./fixtures";

const shots = process.env.EPV_SHOTS;
async function shot(page: Page, name: string) {
  if (shots) await page.screenshot({ path: `${shots}/${name}.png`, fullPage: false });
}

async function submitBatch(page: Page, rows: unknown[]) {
  await page.goto("/intake");
  // A JSON array is a batch even with one row; one bare object would be a single receipt.
  await page.getByLabel("Receipt JSON or batch").fill(rows.length > 1 ? jsonl(rows) : JSON.stringify(rows));
  await page.getByRole("button", { name: "Submit batch" }).click();
  await expect(page.getByRole("region", { name: "Batch result" })).toBeVisible();
}

async function waitForState(page: Page, id: string, text: string) {
  await page.goto(`/all/${id}`);
  await expect(page.getByRole("region", { name: `Receipt ${id}` }).locator(".state-chip")).toHaveText(text, { timeout: 20_000 });
}

test.describe.configure({ mode: "serial" });

test("empty screens say what is done and what is next", async ({ page }) => {
  await page.goto("/queue");
  await expect(page.getByText("Queue clear. Nothing is waiting for your decision.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Submit one or a batch" })).toBeVisible();
  await shot(page, "01-queue-empty");
  await page.goto("/evaluation");
  await expect(page.getByText("No measurements loaded yet.")).toBeVisible();
  await page.goto("/insights");
  await expect(page.getByText("No receipts yet.")).toBeVisible();
  await expect(page.locator(".nav__health")).toContainText("API connected");
});

test("intake: a batch with one bad row is a partial success", async ({ page }) => {
  await page.goto("/intake");
  await page.getByRole("button", { name: "Load a sample batch" }).click();
  await expect(page.getByText("A batch of 3 rows (JSON Lines)")).toBeVisible();
  await page.getByRole("button", { name: "Submit batch" }).click();
  const result = page.getByRole("region", { name: "Batch result" });
  await expect(result).toContainText("1 refused");
  await expect(result.locator(".outcome--invalid")).toHaveText("Refused");
  await expect(result.getByRole("link", { name: "SAMPLE-001" })).toBeVisible();
  await expect(result.getByText("Done.")).toBeVisible({ timeout: 20_000 });
  await shot(page, "02-intake-batch");
  // Submitting the same batch again starts no new work.
  await page.getByRole("button", { name: "Submit batch" }).click();
  await expect(page.getByRole("region", { name: "Batch result" }).getByText("Already known").first()).toBeVisible();
});

test("intake: one receipt, repeated, then revised", async ({ page }) => {
  await page.goto("/intake");
  await page.getByLabel("Receipt JSON or batch").fill(JSON.stringify(receipt("E2E-REV")));
  await page.getByRole("button", { name: "Submit receipt" }).click();
  await expect(page.getByRole("region", { name: "Submission result" })).toContainText("Accepted");
  await page.getByRole("button", { name: "Submit receipt" }).click();
  await expect(page.getByRole("region", { name: "Submission result" })).toContainText("Already known");
  await page.getByLabel("Receipt JSON or batch").fill(JSON.stringify(receipt("E2E-REV", { merchant_name: "Other Shop" })));
  await page.getByRole("button", { name: "Submit receipt" }).click();
  await expect(page.getByRole("region", { name: "Submission result" })).toContainText("New revision");
  await waitForState(page, "E2E-REV", "In review");
  await expect(page.locator(".verdict .tag", { hasText: "revision 2" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Revisions" })).toBeVisible();
});

test("intake: invalid input is explained, not sent", async ({ page }) => {
  await page.goto("/intake");
  await page.getByLabel("Receipt JSON or batch").fill("hello there");
  await expect(page.getByRole("button", { name: /Submit/ }).first()).toBeDisabled();
  await page.getByLabel("Receipt JSON or batch").fill('{"receipt_id": "E2E-BAD"}');
  await page.getByRole("button", { name: "Submit receipt" }).click();
  await expect(page.getByRole("alert")).toContainText("Not submitted");
  await expect(page.getByRole("alert").locator("code").first()).toBeVisible();
});

test("workbench: a category correction raises a finding with the policy text, and rejecting confirms the flag", async ({ page }) => {
  await submitBatch(page, [apac("E2E-APAC")]);
  await waitForState(page, "E2E-APAC", "In review");
  const pane = page.getByRole("region", { name: "Receipt E2E-APAC" });
  await expect(pane.getByText("Needs a person to look")).toBeVisible();

  await page.getByRole("button", { name: "Correct the category of E2E-APAC-L2" }).click();
  const dlg = page.getByRole("dialog");
  await dlg.getByLabel("Correct category").selectOption("alcohol");
  await dlg.getByLabel("Your name").fill("Ada Auditor");
  await dlg.getByRole("button", { name: "Correct a category" }).click();

  const finding = pane.getByRole("article", { name: "Finding REG-01" });
  await expect(finding).toBeVisible();
  await expect(finding).toContainText("Alcohol is never reimbursable for APAC-entity employees");
  await expect(pane.locator(".ll-badge--flag").first()).toBeVisible();
  await shot(page, "03-workbench-flag");

  // Confirming the flag (reject) matches the proposal, so no reason is needed.
  await page.keyboard.press("r");
  await page.getByRole("dialog").getByRole("button", { name: "Reject" }).click();
  await expect(pane.locator(".state-chip")).toHaveText("Rejected");
  await expect(pane.getByText("Rejected", { exact: true }).first()).toBeVisible();
  await expect(pane.locator(".timeline")).toContainText("Category of E2E-APAC-L2 changed");
  await expect(pane.getByText("This receipt is closed.")).toBeVisible();
});

test("workbench: approving a flag is an override and needs a reason", async ({ page }) => {
  await submitBatch(page, [apac("E2E-OVR")]);
  await waitForState(page, "E2E-OVR", "In review");
  await page.getByRole("button", { name: "Correct the category of E2E-OVR-L2" }).click();
  await page.getByRole("dialog").getByLabel("Correct category").selectOption("alcohol");
  await page.getByRole("dialog").getByLabel("Your name").fill("Ada Auditor");
  await page.getByRole("dialog").getByRole("button", { name: "Correct a category" }).click();
  const pane = page.getByRole("region", { name: "Receipt E2E-OVR" });
  await expect(pane.getByRole("article", { name: "Finding REG-01" })).toBeVisible();

  await pane.getByRole("button", { name: /^Approve/ }).click();
  const dlg = page.getByRole("dialog");
  await expect(dlg).toContainText("goes against that proposal");
  await dlg.getByRole("button", { name: "Approve" }).click();
  await expect(dlg.getByRole("alert")).toContainText("Choose a reason");
  await dlg.getByLabel("Reason").selectOption("policy_exception_granted");
  await dlg.getByRole("button", { name: "Approve" }).click();
  await expect(pane.locator(".state-chip")).toHaveText("Approved");
  await expect(pane.locator(".timeline")).toContainText("Policy exception granted");
});

test("workbench: a stale decision is refused with a clear message", async ({ page, request }) => {
  await submitBatch(page, [apac("E2E-STALE")]);
  await waitForState(page, "E2E-STALE", "In review");
  const pane = page.getByRole("region", { name: "Receipt E2E-STALE" });
  await expect(pane.getByRole("button", { name: /^Approve/ })).toBeVisible();
  // Someone else corrects a category while this auditor is reading version 1.
  const api = `http://localhost:8777`;
  const res = await request.post(`${api}/receipts/E2E-STALE/actions/correct-category`, {
    data: { actor: "colleague", evaluation_version: 1, line_id: "E2E-STALE-L2", category: "alcohol" },
  });
  expect(res.ok()).toBeTruthy();
  await pane.getByRole("button", { name: /^Reject/ }).click();
  const dlg = page.getByRole("dialog");
  await dlg.getByLabel("Your name").fill("Ada Auditor");
  await dlg.getByRole("button", { name: "Reject" }).click();
  await expect(dlg.getByRole("alert")).toContainText("re-evaluated while you were looking");
  await dlg.getByRole("button", { name: "Close and read the new result" }).click();
  await expect(pane.getByRole("article", { name: "Finding REG-01" })).toBeVisible();
});

test("workbench: request information, then escalate another receipt to Compliance", async ({ page }) => {
  await submitBatch(page, [receipt("E2E-INFO"), receipt("E2E-ESC")]);
  await waitForState(page, "E2E-INFO", "In review");
  await page.getByRole("button", { name: /^Request information/ }).click();
  let dlg = page.getByRole("dialog");
  await dlg.getByLabel("Question for the employee").fill("Please attach the itemized invoice.");
  await dlg.getByLabel("Your name").fill("Ada Auditor");
  await dlg.getByRole("button", { name: "Request information" }).last().click();
  await expect(page.getByText("Waiting for information.")).toBeVisible();
  await expect(page.getByText("Please attach the itemized invoice.").first()).toBeVisible();

  await waitForState(page, "E2E-ESC", "In review");
  await page.getByRole("button", { name: /^Escalate/ }).click();
  dlg = page.getByRole("dialog");
  await dlg.getByLabel("Why does this need Compliance?").fill("Possible gift to an official.");
  await dlg.getByRole("button", { name: "Escalate to Compliance" }).last().click();
  await expect(page.getByText("With Compliance.")).toBeVisible();
  await page.goto("/compliance");
  await expect(page.getByRole("link", { name: "E2E-ESC" })).toBeVisible();
  await shot(page, "04-compliance");
});

test("queue: keyboard navigation, filters and the quality sample view", async ({ page }) => {
  await page.goto("/queue");
  await expect(page.locator("table.queue tbody tr").first()).toBeVisible();
  await page.keyboard.press("j");
  await expect(page).toHaveURL(/\/queue\/.+/);
  await page.getByRole("button", { name: "Proposed pass" }).click();
  await expect(page.getByText("No receipt matches these filters.")).toBeVisible();
  await page.getByRole("button", { name: "All proposals" }).click();
  await page.keyboard.press("?");
  await expect(page.getByRole("dialog")).toContainText("Keyboard shortcuts");
  await page.keyboard.press("Escape");
  await page.goto("/sample");
  await expect(page.getByRole("heading", { name: "Quality sample" })).toBeVisible();
});

test("insights, history and theme", async ({ page }) => {
  await page.goto("/insights");
  await expect(page.getByText(/N = \d+ decisions?/)).toBeVisible();
  await expect(page.getByRole("heading", { name: /Receipts by state/ })).toBeVisible();
  await shot(page, "05-insights");
  await page.goto("/all");
  await page.getByLabel("State").selectOption("rejected");
  await expect(page.getByRole("link", { name: "E2E-APAC" })).toBeVisible();
  await page.getByRole("button", { name: /Theme:/ }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.getByRole("button", { name: /Theme:/ }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await shot(page, "06-all-dark");
});

test("narrow screens: the detail replaces the list, with a way back", async ({ page }) => {
  await page.setViewportSize({ width: 600, height: 900 });
  await page.goto("/all/E2E-APAC");
  await expect(page.getByRole("region", { name: "Receipt E2E-APAC" })).toBeVisible();
  await expect(page.locator("table.queue")).toBeHidden();
  await page.getByRole("link", { name: "← Back to the list" }).click();
  await expect(page.locator("table.queue")).toBeVisible();
});
