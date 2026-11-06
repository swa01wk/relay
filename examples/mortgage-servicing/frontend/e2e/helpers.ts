import { expect } from "@playwright/test";

export async function connectSession(page: import("@playwright/test").Page) {
  await page.goto("http://localhost:3000");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(page.getByTestId("connection-state")).toContainText("ready", { timeout: 15_000 });
  await expect(page.getByText("Session ready.")).toBeVisible({ timeout: 15_000 });
}

/** Wait for Rajesh case UI and for the opening turn to finish (WS user text is async). */
export async function openRajeshCase(page: import("@playwright/test").Page) {
  // Send stays disabled while the input is empty, so wait on the assistant reply instead.
  const assistantMessages = page.locator('[data-testid="chat-message"][data-chat-role="assistant"]');
  const before = await assistantMessages.count();
  await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Find Rajesh Sharma");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByTestId("mortgage-case-view")).toBeVisible({ timeout: 30_000 });
  await expect.poll(async () => assistantMessages.count(), { timeout: 30_000 }).toBeGreaterThan(before);
}
