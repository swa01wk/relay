import { expect, test } from "@playwright/test";

import { connectSession, openRajeshCase } from "./helpers";

const LEAK_PATTERNS = /routed handler|can't sync|cannot sync|based_on_version|STATE_CONFLICT/i;

function lastAssistantMessage(page: import("@playwright/test").Page) {
  return page.locator('[data-testid="chat-message"][data-chat-role="assistant"]').last();
}

/**
 * Text equivalents of [UAT_VOICE_SCRIPT.md](../../../../plans/UAT_VOICE_SCRIPT.md) rows 4–8.
 * Requires gateway @ :8080 and `pnpm dev` @ :3000.
 */
test.describe("UAT mortgage script (text)", () => {
  test.skip(!process.env.PLAYWRIGHT_E2E, "set PLAYWRIGHT_E2E=1 with stack running");

  test("UAT row 4 — compare last 3 months payments", async ({ page }) => {
    await connectSession(page);
    await openRajeshCase(page);

    await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Compare last 3 months payments");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(
      page.locator('[data-testid="chat-message"][data-chat-role="assistant"]').last(),
    ).toContainText(/2847\.50|MORT-2931/i, { timeout: 30_000 });
  });

  test("UAT row 5 — compare payments and rate history", async ({ page }) => {
    await connectSession(page);
    await openRajeshCase(page);

    await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill(
      "Compare payments and rate history for this mortgage",
    );
    await page.getByRole("button", { name: "Send", exact: true }).click();

    const activityPanel = page.getByTestId("activity-panel");
    await expect(activityPanel.getByTestId("activity-row")).toBeVisible({ timeout: 30_000 });
    await expect(activityPanel.getByTestId("activity-row")).toContainText(/done|100%/i, {
      timeout: 30_000,
    });

    await expect(page.getByTestId("rate-history-view")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("rate-history-view")).toContainText("6.125");
    await expect(page.getByText(/2847\.50/i)).toBeVisible({ timeout: 15_000 });
  });

  test("UAT row 3 — customer email from case context", async ({ page }) => {
    await connectSession(page);
    await openRajeshCase(page);

    await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("What is his email?");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(lastAssistantMessage(page)).toContainText("rajesh.sharma@example.com", {
      timeout: 30_000,
    });
  });

  test("UAT rows 7–8 — show rate history then explain from shared state", async ({ page }) => {
    await connectSession(page);
    await openRajeshCase(page);

    await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Show rate history");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(page.getByTestId("rate-history-view")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("rate-history-view")).toContainText("6.125");

    await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("So what was it in 2024?");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(page.locator('[data-testid="chat-message"][data-chat-role="assistant"]').last()).toContainText(
      /5\.875|2024/,
      { timeout: 30_000 },
    );
    await expect(lastAssistantMessage(page)).not.toContainText(/no 2024|don't have.*2024/i);
    await expect(lastAssistantMessage(page)).not.toContainText(LEAK_PATTERNS);
  });

  test("UAT row 11 — correction draft March date (text path)", async ({ page }) => {
    await connectSession(page);
    await openRajeshCase(page);

    await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Prepare correction draft");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(page.getByTestId("correction-draft-view")).toBeVisible({ timeout: 30_000 });

    await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Change it to March, not January.");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(page.getByTestId("correction-effective-date")).toHaveValue("2025-03-01", {
      timeout: 30_000,
    });
    await expect(lastAssistantMessage(page)).not.toContainText(LEAK_PATTERNS);
  });
});
