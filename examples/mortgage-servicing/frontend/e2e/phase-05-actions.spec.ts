import { expect, test } from "@playwright/test";

/**
 * P05-TC-001–003 — text path: search Rajesh → open MORT-2931 → shared state panel.
 * Requires gateway @ :8080 and `pnpm dev` @ :3000.
 */
test.describe("Phase 5 typed actions", () => {
  test.skip(!process.env.PLAYWRIGHT_E2E, "set PLAYWRIGHT_E2E=1 with stack running");

  test("Find Rajesh Sharma opens case with shared state", async ({ page }) => {
    await page.goto("http://localhost:3000");
    await page.getByRole("button", { name: "Connect", exact: true }).click();
    await expect(page.getByText("RP:")).toContainText("ready", { timeout: 15_000 });
    await expect(page.getByText("Session ready.")).toBeVisible({ timeout: 15_000 });

    await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Find Rajesh Sharma");
    await page.getByRole("button", { name: "Send", exact: true }).click();

    // Agent may flash search results then OPEN_ENTITY navigates to case (single screen slot).
    await expect(page.getByTestId("mortgage-case-view")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("mortgage-case-view")).toContainText("MORT-2931");
    await expect(page.getByTestId("mortgage-case-view")).toContainText("Rajesh Sharma");

    const statePanel = page.getByTestId("shared-state-panel");
    await expect(statePanel).toContainText('"screen": "mortgage_case"');
    await expect(statePanel).toContainText("MORT-2931");
  });
});
