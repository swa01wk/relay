import { expect, test } from "@playwright/test";

import { connectSession, openRajeshCase } from "./helpers";

const LEAK_PATTERNS = /routed handler|can't sync|cannot sync|based_on_version|STATE_CONFLICT|apply_state_delta/i;

async function prepareDraft(page: import("@playwright/test").Page) {
  await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Prepare correction draft");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByTestId("correction-draft-view")).toBeVisible({ timeout: 30_000 });
}

/** Edit effective date during the slow prepare_correction window (5s server-side). */
async function editEffectiveDateDuringSlowPrepare(
  page: import("@playwright/test").Page,
  effectiveDate: string,
) {
  await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Prepare correction draft slow");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByTestId("correction-draft-view")).toBeVisible({ timeout: 30_000 });

  const dateInput = page.getByTestId("correction-effective-date");
  const deadline = Date.now() + 12_000;
  while (Date.now() < deadline) {
    if (await dateInput.isVisible()) {
      await dateInput.fill(effectiveDate);
      await dateInput.dispatchEvent("change");
      await dateInput.press("Tab");
      return;
    }
    await page.waitForTimeout(25);
  }
  throw new Error("correction-effective-date never became visible during slow prepare");
}

async function expectConflictSignal(page: import("@playwright/test").Page) {
  await expect
    .poll(
      async () =>
        page.evaluate(() => (window as Window & { __relayConflictCount?: number }).__relayConflictCount ?? 0),
      { timeout: 45_000 },
    )
    .toBeGreaterThan(0);
  await expect(page.getByTestId("state-conflict-banner")).toBeVisible({ timeout: 5_000 });
}

async function resetConflictCounter(page: import("@playwright/test").Page) {
  await page.evaluate(() => {
    (window as Window & { __relayConflictCount?: number }).__relayConflictCount = 0;
  });
}

function lastAssistantMessage(page: import("@playwright/test").Page) {
  return page.locator('[data-testid="chat-message"][data-chat-role="assistant"]').last();
}

/**
 * P08-TC-001–003 + UAT-006 (script row #11) — draft correction, human edit during slow tool, guard rails.
 * Requires gateway @ :8080 and `pnpm dev` @ :3000.
 */
test.describe("Phase 8 state versioning", () => {
  test.skip(!process.env.PLAYWRIGHT_E2E, "set PLAYWRIGHT_E2E=1 with stack running");

  test.beforeEach(async ({ page }) => {
    await connectSession(page);
    await resetConflictCounter(page);
  });

  test("P08-TC-001b agent text date update syncs draft field", async ({ page }) => {
    await openRajeshCase(page);
    await prepareDraft(page);

    await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("change the date to 01/01/2026");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(page.getByTestId("correction-effective-date")).toHaveValue("2026-01-01", {
      timeout: 30_000,
    });
  });

  test("UAT-006 script row 11 — March phrase updates draft without internal leak", async ({ page }) => {
    await openRajeshCase(page);
    await prepareDraft(page);
    await expect(page.getByTestId("correction-effective-date")).toHaveValue("2025-01-01");

    await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Change it to March, not January.");
    await page.getByRole("button", { name: "Send", exact: true }).click();

    await expect(page.getByTestId("correction-effective-date")).toHaveValue("2025-03-01", {
      timeout: 30_000,
    });
    await expect(lastAssistantMessage(page)).not.toContainText(LEAK_PATTERNS);
    await expect(lastAssistantMessage(page)).toContainText(/March|2025-03-01|draft/i, {
      timeout: 15_000,
    });
  });

  test("P08-TC-001 edit draft effective date bumps version and EMI", async ({ page }) => {
    await openRajeshCase(page);
    await prepareDraft(page);

    const dateInput = page.getByTestId("correction-effective-date");
    await dateInput.fill("2025-06-15");
    await dateInput.dispatchEvent("change");
    await dateInput.press("Tab");
    await expect(page.getByTestId("correction-projected-emi")).toContainText("$");
    await expect(page.getByTestId("shared-state-panel")).toContainText("2025-06-15", {
      timeout: 10_000,
    });
  });

  test("P08-TC-002 stale agent update shows conflict and keeps human date", async ({ page }) => {
    await openRajeshCase(page);
    await editEffectiveDateDuringSlowPrepare(page, "2025-08-01");
    await expectConflictSignal(page);
    await expect(page.getByTestId("correction-effective-date")).toHaveValue("2025-08-01");
  });

  test("P08-TC-003 post-conflict draft matches edited effective date", async ({ page }) => {
    await openRajeshCase(page);
    await editEffectiveDateDuringSlowPrepare(page, "2025-09-01");
    await expectConflictSignal(page);
    await expect(page.getByTestId("correction-effective-date")).toHaveValue("2025-09-01");
    await expect(page.getByTestId("correction-projected-emi")).toBeVisible();
    await expect(page.getByTestId("shared-state-panel")).toContainText("2025-09-01", {
      timeout: 15_000,
    });
    await expect(lastAssistantMessage(page)).not.toContainText(LEAK_PATTERNS);
  });
});
