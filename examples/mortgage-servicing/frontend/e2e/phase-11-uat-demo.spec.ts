import { test, expect } from "@playwright/test";

/**
 * P11-TC-001 (staged, text-first) — §12.1 narrative steps 1–15 subset through commit.
 * Voice-first full UAT: manual [UAT_VOICE_SCRIPT.md](../../../plans/UAT_VOICE_SCRIPT.md).
 */
test.describe("Phase 11 — staged UAT demo (text)", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: "Connect" }).click();
    await expect(page.getByText("Session ready.")).toBeVisible({ timeout: 15_000 });
  });

  test("P11-TC-001 staged — Rajesh investigation through commit verify", async ({ page }) => {
    const send = async (text: string) => {
      await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill(text);
      await page.getByRole("button", { name: "Send" }).click();
    };

    await send("Find Rajesh Sharma");
    await expect(page.getByTestId("mortgage-case-view")).toBeVisible({ timeout: 30_000 });

    await send("Compare last 3 months payments");
    await expect(page.getByTestId("chat-message").last()).toBeVisible({ timeout: 30_000 });

    await send("Prepare correction draft");
    await expect(page.getByTestId("correction-draft-view")).toBeVisible({ timeout: 30_000 });

    await send("Submit for approval");
    await expect(page.getByTestId("approval-modal")).toBeVisible({ timeout: 30_000 });
    await page.getByTestId("approval-approve-btn").click();
    await expect(page.getByTestId("commit-verified-banner")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("mortgage-case-view")).toBeVisible();
  });
});
