import { expect, test } from "@playwright/test";

import { connectSession, openRajeshCase } from "./helpers";

/** Generative UI canvas — PRESENT_UI surfaces rendered by the app via registerPlaygroundSurfaces. */
test.describe("Playground canvas", () => {
  test.skip(!process.env.PLAYWRIGHT_E2E, "set PLAYWRIGHT_E2E=1 with stack running");

  test.beforeEach(async ({ page }) => {
    await connectSession(page);
  });

  test("search mirrors results into a canvas table", async ({ page }) => {
    await openRajeshCase(page);
    const canvas = page.getByTestId("playground-canvas");
    await expect(canvas.getByTestId("playground-surface").first()).toBeVisible({ timeout: 15_000 });
    await expect(canvas).toContainText("Rajesh Sharma");
  });

  test("parallel investigation shows payments and rate tables", async ({ page }) => {
    await openRajeshCase(page);
    await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Compare payments and rate history");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    const tables = page.getByTestId("playground-canvas").getByTestId("playground-table");
    await expect(tables).toHaveCount(2, { timeout: 30_000 });
    await expect(page.getByTestId("playground-canvas")).toContainText("2025-09");
    await expect(page.getByTestId("playground-canvas")).toContainText("arm_adjustment");
  });

  test("payments route renders a bar chart and investigation a rate line", async ({ page }) => {
    await openRajeshCase(page);
    const canvas = page.getByTestId("playground-canvas");
    await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Compare last 3 months payments");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(canvas.locator('[data-testid="playground-chart"][data-chart-type="bar"]')).toBeVisible({
      timeout: 30_000,
    });
    await expect(canvas.locator(".recharts-bar-rectangle").first()).toBeVisible();

    await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Compare payments and rate history");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(canvas.locator('[data-testid="playground-chart"][data-chart-type="line"]')).toBeVisible({
      timeout: 30_000,
    });
  });

  test("table filter, sort and CSV export", async ({ page }) => {
    await openRajeshCase(page);
    await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Compare payments and rate history");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    const payments = page
      .getByTestId("playground-surface")
      .filter({ hasText: "Payments — MORT-2931" })
      .filter({ has: page.getByTestId("playground-table") });
    await expect(payments).toBeVisible({ timeout: 30_000 });

    await payments.getByTestId("playground-table-filter").fill("2025-08");
    await expect(payments.getByTestId("playground-table-count")).toHaveText("1/3");
    await payments.getByTestId("playground-table-filter").fill("");

    await payments.getByRole("button", { name: "Month" }).click();
    await expect(payments.locator("tbody tr").first()).toContainText("2025-07");

    const [download] = await Promise.all([
      page.waitForEvent("download"),
      payments.getByTestId("playground-export-csv").click(),
    ]);
    const csv = await (await download.createReadStream()).toArray();
    const text = Buffer.concat(csv).toString("utf8");
    expect(text.split("\r\n")[0]).toBe("Month,Amount,Status,Paid On");
    expect(text).toContain("2025-07,2847.5,paid,2025-07-01");
  });

  test("model-driven comparison and markdown (needs OPENAI_API_KEY)", async ({ page }) => {
    test.skip(!process.env.PLAYWRIGHT_LLM, "set PLAYWRIGHT_LLM=1 when the gateway has a live model key");
    await openRajeshCase(page);
    const input = page.getByPlaceholder('Try "Find Rajesh Sharma"');
    await input.fill("Compare Rajesh's two mortgages side by side");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    const comparison = page.getByTestId("playground-comparison");
    await expect(comparison).toBeVisible({ timeout: 45_000 });
    await expect(comparison).toContainText("MORT-1102");
    await expect(comparison.locator('tr[data-differs="true"]').first()).toBeVisible();

    await input.fill("Write a short markdown summary of this case with a heading and bullet points");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    const markdown = page.getByTestId("playground-markdown");
    await expect(markdown.locator("li").first()).toBeVisible({ timeout: 45_000 });
  });

  test("model-driven form round trip (needs OPENAI_API_KEY)", async ({ page }) => {
    test.skip(!process.env.PLAYWRIGHT_LLM, "set PLAYWRIGHT_LLM=1 when the gateway has a live model key");
    await openRajeshCase(page);
    await page
      .getByPlaceholder('Try "Find Rajesh Sharma"')
      .fill("I want to update Rajesh's contact details, give me a form with email and phone");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    const form = page.getByTestId("playground-form");
    await expect(form).toBeVisible({ timeout: 45_000 });

    await form.locator('input[type="email"]').first().fill("rajesh.new@example.com");
    const phone = form.locator('input[type="tel"], input[type="text"]').first();
    if (await phone.count()) await phone.fill("555-0100");
    await form.getByRole("button").last().click();
    await expect(form.getByTestId("playground-form-submitted")).toBeVisible();

    const userMessages = page.locator('[data-testid="chat-message"][data-chat-role="user"]');
    await expect(userMessages.last()).toContainText("[Form submitted]", { timeout: 15_000 });
    await expect(userMessages.last()).toContainText("rajesh.new@example.com");
    await expect(page.locator('[data-testid="chat-message"][data-chat-role="assistant"]').last()).not.toBeEmpty({
      timeout: 45_000,
    });
  });

  test("model-driven chart on a free-form request (needs OPENAI_API_KEY)", async ({ page }) => {
    test.skip(!process.env.PLAYWRIGHT_LLM, "set PLAYWRIGHT_LLM=1 when the gateway has a live model key");
    await openRajeshCase(page);
    await page
      .getByPlaceholder('Try "Find Rajesh Sharma"')
      .fill("Plot how the interest rate on this mortgage changed over time");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(page.getByTestId("playground-canvas").getByTestId("playground-chart")).toBeVisible({
      timeout: 45_000,
    });
  });

  test("model-driven table on a free-form request (needs OPENAI_API_KEY)", async ({ page }) => {
    test.skip(!process.env.PLAYWRIGHT_LLM, "set PLAYWRIGHT_LLM=1 when the gateway has a live model key");
    await openRajeshCase(page);
    await page
      .getByPlaceholder('Try "Find Rajesh Sharma"')
      .fill("Give me a table of the audit history for this mortgage");
    await page.getByRole("button", { name: "Send", exact: true }).click();
    await expect(page.getByTestId("playground-canvas")).toContainText(/payment_posted|rate_lookup/, {
      timeout: 45_000,
    });
  });
});
