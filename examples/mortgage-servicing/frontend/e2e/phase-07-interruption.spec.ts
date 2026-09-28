import { expect, test } from "@playwright/test";

async function connectSession(page: import("@playwright/test").Page) {
  await page.goto("http://localhost:3000");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(page.getByText("RP:")).toContainText("ready", { timeout: 15_000 });
  await expect(page.getByText("Session ready.")).toBeVisible({ timeout: 15_000 });
}

/**
 * P07-TC-003 — post-interrupt rate history via text (voice barge-in covered in runtime pytest).
 */
test.describe("Phase 7 interruption + heard-truth", () => {
  test.skip(!process.env.PLAYWRIGHT_E2E, "set PLAYWRIGHT_E2E=1 with stack running");

  test("P07-TC-003 rate history after interrupt-style follow-up", async ({ page }) => {
    await connectSession(page);

    await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Find Rajesh Sharma");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(page.getByTestId("mortgage-case-view")).toBeVisible({ timeout: 30_000 });

    await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Show rate history");
    await page.getByRole("button", { name: "Send", exact: true }).click();

    await expect(page.getByTestId("rate-history-view")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("rate-history-view")).toContainText("6.125");
  });
});
