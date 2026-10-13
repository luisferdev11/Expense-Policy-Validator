import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
import { apac, jsonl, receipt } from "./fixtures";

const shots = process.env.EPV_SHOTS;
async function shot(page: Page, name: string, fullPage = false) {
  if (shots) await page.screenshot({ path: `${shots}/${name}.png`, fullPage });
}

async function submitBatch(page: Page, rows: unknown[]) {
  await page.goto("/intake");
  // A JSON array is a batch even with one row; one bare object would be a single receipt.
  await page.getByLabel("Receipt JSON or batch").fill(rows.length > 1 ? jsonl(rows) : JSON.stringify(rows));
  await page.getByRole("button", { name: "Validate" }).click();
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
  await expect(page.getByRole("heading", { name: "Five classifiers on the frozen dev set" })).toBeVisible();
  await page.goto("/insights");
  await expect(page.getByText("No receipts yet.")).toBeVisible();
  await expect(page.locator(".nav__health")).toContainText("API connected");
});

test("intake: a batch with one bad row is a partial success", async ({ page }) => {
  await page.goto("/intake");
  await page.getByRole("button", { name: "Load a sample batch" }).click();
  await expect(page.getByText("A batch of 3 rows (JSON Lines)")).toBeVisible();
  await page.getByRole("button", { name: "Validate" }).click();
  const result = page.getByRole("region", { name: "Batch result" });
  await expect(result).toContainText("1 refused");
  await expect(result.locator(".outcome--invalid")).toHaveText("Rejected, not saved");
  await expect(result.getByRole("link", { name: "SAMPLE-001" })).toBeVisible();
  await expect(result.getByText("Done.")).toBeVisible({ timeout: 20_000 });
  await shot(page, "02-intake-batch");
  const dl = page.waitForEvent("download");
  await result.getByRole("button", { name: "Download rejected rows" }).click();
  expect((await dl).suggestedFilename()).toMatch(/refused\.jsonl$/);
  await result.getByRole("link", { name: "Open in the review queue" }).click();
  await expect(page).toHaveURL(/\/all\?batch=bat_/);
  await expect(page.getByText("Showing only batch")).toBeVisible();
  await expect(page.locator("table.queue tbody tr")).toHaveCount(2);
  await page.goBack();
  // Submitting the same batch again starts no new work.
  await page.getByRole("button", { name: "Load a sample batch" }).click();
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByRole("region", { name: "Batch result" }).getByText(/already known/i).first()).toBeVisible();
});

test("intake: one receipt, repeated, then revised", async ({ page }) => {
  await page.goto("/intake");
  await page.getByLabel("Receipt JSON or batch").fill(JSON.stringify(receipt("E2E-REV")));
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByRole("region", { name: "Submission result" })).toContainText("Accepted");
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByRole("region", { name: "Submission result" })).toContainText("Already known");
  await page.getByLabel("Receipt JSON or batch").fill(JSON.stringify(receipt("E2E-REV", { merchant_name: "Other Shop" })));
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByRole("region", { name: "Submission result" })).toContainText("New revision");
  await waitForState(page, "E2E-REV", "In review");
  await expect(page.locator(".verdict .tag", { hasText: "revision 2" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Revisions" })).toBeVisible();
});

// Spec 008: the guided form. Each test uses its own receipt ID and does not need the others.
async function fillHeader(page: Page, id: string) {
  await page.getByLabel("Receipt ID", { exact: true }).fill(id);
  await page.getByLabel("Employee ID", { exact: true }).fill("E-FORM");
  await page.getByLabel("Employee's home country", { exact: true }).fill("US");
  await page.getByLabel("Declared expense type", { exact: true }).fill("Office Supplies");
  await page.getByLabel("Merchant", { exact: true }).fill("Form Stationers");
  await page.getByLabel("MCC", { exact: true }).fill("5943");
  await page.getByLabel("MCC description", { exact: true }).fill("Office supply stores");
}

test("form: fill and submit a two-line receipt", async ({ page }) => {
  await page.goto("/intake");
  await page.getByRole("button", { name: "One receipt (form)" }).click();
  await fillHeader(page, "E2E-FORM-1");
  await expect(page.getByLabel("Regional entity", { exact: true })).toHaveValue("GLOBAL");

  const line1 = page.getByRole("group", { name: "Line 1" });
  await line1.getByLabel("Description (as printed)", { exact: true }).fill("Pens box of 12");
  await line1.getByLabel("Quantity", { exact: true }).fill("2");
  await line1.getByLabel("Unit price", { exact: true }).fill("15.00");
  await page.getByRole("button", { name: "Add line" }).click();
  const line2 = page.getByRole("group", { name: "Line 2" });
  await expect(line2.getByLabel("Description (as printed)", { exact: true })).toBeFocused();
  await line2.getByLabel("Description (as printed)", { exact: true }).fill("Legal pads");
  await line2.getByLabel("Unit price", { exact: true }).fill("12.50");

  await expect(line1.getByLabel("Amount", { exact: true })).toHaveValue("30.00");
  await expect(page.getByLabel("Total (receipt currency)", { exact: true })).toHaveValue("42.50");
  await expect(page.getByLabel("Total in USD", { exact: true })).toHaveValue("42.50");

  await page.getByText("Preview JSON").click();
  await expect(page.locator("pre.json-preview")).toContainText('"line_id": "E2E-FORM-1-L2"');

  // Keyboard only: Enter in an input sends the form.
  await page.getByLabel("Merchant", { exact: true }).press("Enter");
  const result = page.getByRole("region", { name: "Submission result" });
  await expect(result).toContainText("Accepted");
  await page.getByLabel("Merchant", { exact: true }).press("Enter");
  await expect(result).toContainText("Already known");
  await shot(page, "09-intake-form");
});

test("form: errors are shown per field and nothing is sent", async ({ page }) => {
  const posts: string[] = [];
  page.on("request", (r) => {
    if (r.method() === "POST" && r.url().includes("/api/receipts")) posts.push(r.url());
  });
  await page.goto("/intake");
  await page.getByRole("button", { name: "One receipt (form)" }).click();
  await fillHeader(page, "E2E-FORM-ERR");
  await page.getByLabel("Employee ID", { exact: true }).fill("");
  const line1 = page.getByRole("group", { name: "Line 1" });
  await line1.getByLabel("Description (as printed)", { exact: true }).fill("Pens");
  await line1.getByLabel("Quantity", { exact: true }).fill("0");
  await line1.getByLabel("Unit price", { exact: true }).fill("5");

  await page.getByRole("button", { name: "Validate" }).click();
  const summary = page.getByRole("alert");
  await expect(summary).toContainText("Fix these before sending");
  await expect(summary.getByRole("link")).toHaveCount(2);
  await expect(page.getByLabel("Employee ID", { exact: true })).toHaveAttribute("aria-invalid", "true");
  await expect(line1.getByLabel("Quantity", { exact: true })).toHaveAttribute("aria-invalid", "true");
  await expect(line1).toContainText("Must be greater than 0");
  await summary.getByRole("link", { name: /Employee ID/ }).click();
  await expect(page.getByLabel("Employee ID", { exact: true })).toBeFocused();
  expect(posts).toHaveLength(0);
});

test("form: a draft survives a reload and can be discarded", async ({ page }) => {
  await page.goto("/intake");
  await page.getByRole("button", { name: "One receipt (form)" }).click();
  await page.getByLabel("Receipt ID", { exact: true }).fill("E2E-FORM-DRAFT");
  await page.getByLabel("Employee ID", { exact: true }).fill("E-DRAFT");
  await page.getByLabel("Merchant", { exact: true }).fill("Draft Cafe");
  await page.getByRole("group", { name: "Line 1" }).getByLabel("Description (as printed)", { exact: true }).fill("Coffee");
  await page.getByRole("button", { name: "Add line" }).click();
  await page.getByRole("group", { name: "Line 2" }).getByLabel("Description (as printed)", { exact: true }).fill("Bagel");

  await page.reload();
  await expect(page.getByRole("button", { name: "One receipt (form)" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText(/Draft restored from/)).toBeVisible();
  await expect(page.getByLabel("Receipt ID", { exact: true })).toHaveValue("E2E-FORM-DRAFT");
  await expect(page.getByLabel("Employee ID", { exact: true })).toHaveValue("E-DRAFT");
  await expect(page.getByLabel("Merchant", { exact: true })).toHaveValue("Draft Cafe");
  await expect(page.getByRole("group", { name: "Line 1" }).getByLabel("Description (as printed)", { exact: true })).toHaveValue("Coffee");
  await expect(page.getByRole("group", { name: "Line 2" }).getByLabel("Description (as printed)", { exact: true })).toHaveValue("Bagel");

  await page.getByRole("button", { name: "Discard draft" }).click();
  await expect(page.getByLabel("Receipt ID", { exact: true })).toHaveValue("");
  await expect(page.getByRole("group", { name: "Line 2" })).toHaveCount(0);
  await expect(page.getByText(/Draft restored from/)).toHaveCount(0);

  await page.reload();
  await expect(page.getByText(/Draft restored from/)).toHaveCount(0);
  // Nothing was kept, so the screen opens on its default mode with an empty form behind the chip.
  await page.getByRole("button", { name: "One receipt (form)" }).click();
  await expect(page.getByLabel("Receipt ID", { exact: true })).toHaveValue("");
});

test("form: a sent receipt leaves no draft behind", async ({ page }) => {
  await page.goto("/intake");
  await page.getByRole("button", { name: "One receipt (form)" }).click();
  await fillHeader(page, "E2E-FORM-SENT");
  const line1 = page.getByRole("group", { name: "Line 1" });
  await line1.getByLabel("Description (as printed)", { exact: true }).fill("Stapler");
  await line1.getByLabel("Unit price", { exact: true }).fill("9.99");
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByRole("region", { name: "Submission result" })).toContainText("Accepted");
  await page.waitForTimeout(700); // longer than the 400 ms save delay
  await page.reload();
  await expect(page.getByText(/Draft restored from/)).toHaveCount(0);
});

test("form: revise opens the stored receipt in the form", async ({ page }) => {
  await page.goto("/intake");
  await page.getByRole("button", { name: "One receipt (JSON)" }).click();
  await page.getByLabel("Receipt JSON or batch").fill(JSON.stringify(receipt("E2E-FORM-REV")));
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByRole("region", { name: "Submission result" })).toContainText("Accepted");

  await page.goto("/intake?revise=E2E-FORM-REV");
  await expect(page.getByRole("button", { name: "One receipt (form)" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByLabel("Merchant", { exact: true })).toHaveValue("E2E Stationers");
  await expect(page.getByRole("group", { name: "Line 2" }).getByLabel("Line ID", { exact: true })).toHaveValue("E2E-FORM-REV-L2");
  // Opening a receipt to revise it must not touch the draft, and the form must not invent a change.
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByRole("region", { name: "Submission result" })).toContainText("Already known");
  await page.getByLabel("Merchant", { exact: true }).fill("Revised Stationers");
  await page.getByRole("button", { name: "Validate" }).click();
  await expect(page.getByRole("region", { name: "Submission result" })).toContainText("New revision");
});

test("form: the form and the JSON text convert both ways", async ({ page }) => {
  await page.goto("/intake");
  await page.getByRole("button", { name: "One receipt (form)" }).click();
  await fillHeader(page, "E2E-FORM-JSON");
  await page.getByRole("group", { name: "Line 1" }).getByLabel("Description (as printed)", { exact: true }).fill("Tape");
  await page.getByRole("group", { name: "Line 1" }).getByLabel("Unit price", { exact: true }).fill("3.00");
  await page.getByRole("button", { name: "Open as JSON" }).click();
  await expect(page.getByRole("button", { name: "One receipt (JSON)" })).toHaveAttribute("aria-pressed", "true");
  const box = page.getByLabel("Receipt JSON or batch");
  await expect(box).toHaveValue(/"receipt_id": "E2E-FORM-JSON"/);

  // An answer key in the text is not carried into the form, and the person is told.
  const body = JSON.parse(await box.inputValue()) as Record<string, unknown>;
  await box.fill(JSON.stringify({ ...body, labels: { x: 1 } }));
  await page.getByRole("button", { name: "Edit in the form" }).click();
  await expect(page.getByRole("button", { name: "One receipt (form)" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("1 key not shown in the form was dropped")).toBeVisible();
  await expect(page.getByLabel("Receipt ID", { exact: true })).toHaveValue("E2E-FORM-JSON");
});

test("history: events, what a revision changed, and the evaluation versions", async ({ page }) => {
  await page.goto("/history/E2E-REV");
  await expect(page.getByRole("heading", { name: /E2E-REV · history/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Revision 1 → 2" })).toBeVisible();
  await expect(page.locator("table").filter({ hasText: "merchant_name" })).toContainText("Other Shop");
  await expect(page.getByRole("heading", { name: "Evaluation versions" })).toBeVisible();
  await expect(page.locator(".timeline")).toContainText("replaced by revision 2");
  await shot(page, "07-history");
});

test("intake: invalid input is explained, not sent", async ({ page }) => {
  await page.goto("/intake");
  await page.getByLabel("Receipt JSON or batch").fill("hello there");
  await expect(page.getByRole("button", { name: "Validate" })).toBeDisabled();
  await page.getByLabel("Receipt JSON or batch").fill('{"receipt_id": "E2E-BAD"}');
  await page.getByRole("button", { name: "Validate" }).click();
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
  await dlg.getByRole("button", { name: "Re-run the rules" }).click();

  const finding = pane.getByRole("article", { name: "Finding REG-01" });
  await expect(finding).toBeVisible();
  await expect(finding).toContainText("Alcohol is never reimbursable for APAC-entity employees");
  await expect(pane.locator(".ll-badge--flag").first()).toBeVisible();
  await shot(page, "03-workbench-flag");

  // Confirming the flag (reject) matches the proposal, so no reason is needed.
  await page.keyboard.press("r");
  await page.getByRole("dialog").getByRole("button", { name: "Reject expense" }).click();
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
  await page.getByRole("dialog").getByRole("button", { name: "Re-run the rules" }).click();
  const pane = page.getByRole("region", { name: "Receipt E2E-OVR" });
  await expect(pane.getByRole("article", { name: "Finding REG-01" })).toBeVisible();

  await pane.getByRole("button", { name: /^Approve/ }).click();
  const dlg = page.getByRole("dialog");
  await expect(dlg).toContainText("goes against that proposal");
  await dlg.getByRole("button", { name: "Approve anyway" }).click();
  await expect(dlg.getByRole("alert")).toContainText("Choose a reason");
  await dlg.getByLabel("Reason").selectOption("policy_exception_granted");
  await dlg.getByRole("button", { name: "Approve anyway" }).click();
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
  await dlg.getByRole("button", { name: "Reject expense" }).click();
  await expect(dlg.getByRole("alert")).toContainText("re-evaluated while you were looking");
  await dlg.getByRole("button", { name: "Close and read the new result" }).click();
  await expect(pane.getByRole("article", { name: "Finding REG-01" })).toBeVisible();
});

test("workbench: request information, then escalate another receipt to Compliance", async ({ page }) => {
  await submitBatch(page, [receipt("E2E-INFO"), receipt("E2E-ESC")]);
  await waitForState(page, "E2E-INFO", "In review");
  await page.getByRole("button", { name: /^Request information/ }).click();
  let dlg = page.getByRole("dialog");
  await dlg.getByLabel(/Message to/).fill("Please attach the itemized invoice.");
  await dlg.getByLabel("Your name").fill("Ada Auditor");
  await dlg.getByRole("button", { name: "Send and hold" }).click();
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

test("deciding opens the next receipt of the queue", async ({ page }) => {
  await submitBatch(page, [receipt("E2E-NEXT-A"), receipt("E2E-NEXT-B")]);
  await waitForState(page, "E2E-NEXT-A", "In review");
  await waitForState(page, "E2E-NEXT-B", "In review");
  await page.goto("/queue/E2E-NEXT-A");
  const pane = page.getByRole("region", { name: "Receipt E2E-NEXT-A" });
  await expect(pane).toBeVisible();
  await pane.getByRole("button", { name: /^Reject expense/ }).click();
  const dlg = page.getByRole("dialog");
  await dlg.getByLabel("Your name").fill("Ada Auditor");
  await dlg.getByRole("button", { name: "Reject expense" }).click();
  await expect(page).not.toHaveURL(/E2E-NEXT-A/);
  await expect(page).toHaveURL(/\/queue\/.+/);
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
  await expect(page.getByRole("note")).toContainText("does not take it off this list");
});

test("how it works and evaluation", async ({ page }) => {
  await page.goto("/how-it-works");
  await expect(page.getByRole("heading", { name: "How a receipt moves" })).toBeVisible();
  await expect(page.getByRole("rowheader", { name: "With Compliance" })).toBeVisible();
  await page.goto("/evaluation");
  await expect(page.getByText("28 of 28").first()).toBeVisible();
  await expect(page.getByRole("rowheader", { name: "jev-1.13", exact: true })).toBeVisible();
  await expect(page.getByText("Reading the jev-1.13 row.")).toBeVisible();
  await expect(page.getByRole("table", { name: "Disposition confusion matrix" })).toBeVisible();
  await expect(page.getByRole("img", { name: /Category accuracy with 95 percent intervals/ })).toBeVisible();
  await shot(page, "08-evaluation", true);
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
