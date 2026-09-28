import { expect, test } from "@playwright/test";

import { connectSession, openRajeshCase } from "./helpers";

/**
 * P06-TC-001–002 — text path: payment compare + parallel payment/rate investigation.
 * Requires gateway @ :8080 and `pnpm dev` @ :3000.
 */
test.describe("Phase 6 parallel tools", () => {
  test.skip(!process.env.PLAYWRIGHT_E2E, "set PLAYWRIGHT_E2E=1 with stack running");

  test("P06-TC-001 compare last 3 months payments", async ({ page }) => {
    await connectSession(page);

    await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Compare last 3 months payments");
    await page.getByRole("button", { name: "Send", exact: true }).click();

    await expect(page.getByText(/2847\.50|MORT-2931/i)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/assistant:/i).first()).toBeVisible();
  });

  test("P06-TC-002 parallel payment and rate fetch updates activity UI", async ({ page }) => {
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
});
