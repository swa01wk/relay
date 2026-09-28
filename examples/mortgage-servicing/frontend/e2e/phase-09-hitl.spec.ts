import { test, expect } from "@playwright/test";

test.describe("Phase 9 — HITL commit + verify", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Connect" }).click();
    await expect(page.getByText("Session ready.")).toBeVisible({ timeout: 15_000 });
  });

  test("P09-TC-001 — approve correction updates draft status", async ({ page }) => {
    await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Find Rajesh Sharma");
    await page.getByRole("button", { name: "Send" }).click();
    await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Prepare correction draft");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByTestId("correction-draft-view")).toBeVisible({ timeout: 30_000 });

    await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Submit for approval");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByTestId("approval-modal")).toBeVisible({ timeout: 30_000 });

    await page.getByTestId("approval-approve-btn").click();
    await expect(page.getByTestId("commit-verified-banner")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("draft-status")).toContainText("committed");
  });

  test("P09-TC-004 — verify after commit matches authoritative case view", async ({ page }) => {
    await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Find Rajesh Sharma");
    await page.getByRole("button", { name: "Send" }).click();
    await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Prepare correction draft");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByTestId("correction-draft-view")).toBeVisible({ timeout: 30_000 });

    await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Submit for approval");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByTestId("approval-modal")).toBeVisible({ timeout: 30_000 });
    await page.getByTestId("approval-approve-btn").click();
    await expect(page.getByTestId("commit-verified-banner")).toBeVisible({ timeout: 30_000 });

    await expect(page.getByTestId("mortgage-case-view")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("case-current-rate")).toContainText("6.125");
    await expect(page.getByTestId("case-current-emi")).toContainText("2847.50");
  });

  test("P09-TC-002 — reject leaves draft", async ({ page }) => {
    await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Find Rajesh Sharma");
    await page.getByRole("button", { name: "Send" }).click();
    await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Prepare correction draft");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByTestId("correction-draft-view")).toBeVisible({ timeout: 30_000 });

    await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Submit for approval");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByTestId("approval-modal")).toBeVisible({ timeout: 30_000 });

    await page.getByTestId("approval-reject-btn").click();
    await expect(page.getByTestId("approval-modal")).toHaveCount(0);
    await expect(page.getByTestId("draft-status")).toContainText("draft");
  });
});
