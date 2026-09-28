# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: phase-08-state-versioning.spec.ts >> Phase 8 state versioning >> P08-TC-003 post-conflict draft matches edited effective date
- Location: e2e/phase-08-state-versioning.spec.ts:110:7

# Error details

```
Error: expect(received).toBeGreaterThan(expected)

Expected: > 0
Received:   0

Call Log:
- Timeout 45000ms exceeded while waiting on the predicate
```

# Page snapshot

```yaml
- generic [ref=e1]:
  - main [ref=e2]:
    - generic [ref=e3]:
      - generic [ref=e4]:
        - heading "Mortgage servicing — tools & investigations" [level=3] [ref=e5]
        - paragraph [ref=e6]: "Phase 8 — draft correction with optimistic state versioning (try: \"Prepare correction draft slow\" on an open case, then edit the effective date while the agent works)."
      - generic [ref=e7]:
        - generic [ref=e8]:
          - button "Check /health" [ref=e9] [cursor=pointer]
          - button "Connect" [ref=e10] [cursor=pointer]
          - button "Connect voice" [ref=e11] [cursor=pointer]
          - button "Disconnect voice" [disabled]
          - button "Mute mic" [disabled]
        - paragraph [ref=e12]:
          - text: "RP:"
          - strong [ref=e13]: ready
          - text: "· Voice:"
          - strong [ref=e14]: disconnected
          - text: · session
          - code [ref=e15]: 92474d4a-7a3c-4cc9-a1d5-55c56318fb72
        - generic [ref=e16]:
          - generic [ref=e17]:
            - paragraph [ref=e18]: Application view
            - generic [ref=e20]:
              - paragraph [ref=e21]: Draft correction — MORT-2931
              - generic [ref=e22]:
                - generic [ref=e23]: Effective date
                - textbox "Effective date" [ref=e24]: 2025-09-01
              - paragraph [ref=e25]: "Projected EMI: $2847.50"
              - paragraph [ref=e26]: Delta $0.00 vs current $2847.50
          - generic [ref=e27]:
            - paragraph [ref=e28]: Agent activity (RP)
            - paragraph [ref=e29]: No in-flight tool activity.
          - generic [ref=e30]:
            - paragraph [ref=e31]: Shared state (RP)
            - generic [active] [ref=e32]: "{ \"screen\": \"correction_draft\", \"workflow\": \"correction_draft\", \"selected_entity\": { \"type\": \"mortgage\", \"id\": \"MORT-2931\" }, \"search_query\": \"Rajesh Sharma\", \"search_results\": [ { \"id\": \"CUST-1001\", \"name\": \"Rajesh Sharma\", \"email\": \"rajesh.sharma@example.com\", \"mortgages\": [ { \"id\": \"MORT-2931\", \"status\": \"active\", \"property\": \"14 Oak Lane, Austin, TX\", \"current_rate\": 6.125, \"emi\": 2847.5 }, { \"id\": \"MORT-1102\", \"status\": \"closed\", \"property\": \"2200 W 5th St, Austin, TX\", \"current_rate\": 4.875, \"emi\": 0 } ] } ], \"case_summary\": { \"id\": \"MORT-2931\", \"status\": \"active\", \"property\": \"14 Oak Lane, Austin, TX\", \"current_rate\": 6.125, \"emi\": 2847.5, \"customer_name\": \"Rajesh Sharma\", \"customer_id\": \"CUST-1001\" }, \"rate_history\": [], \"correction_draft\": { \"mortgage_id\": \"MORT-2931\", \"effective_date\": \"2025-09-01\", \"status\": \"draft\", \"proposed_rate\": 6.125, \"current_rate\": 6.125, \"current_emi\": 2847.5, \"projected_emi\": 2847.5, \"estimated_emi_delta\": 0 }, \"activities\": [] }"
        - generic [ref=e33]:
          - generic [ref=e34]:
            - generic [ref=e35]: "system:"
            - text: Session ready.
          - generic [ref=e36]:
            - generic [ref=e37]: "user:"
            - text: Find Rajesh Sharma
          - generic [ref=e38]:
            - generic [ref=e39]: "assistant:"
            - text: I found 1 customer match for 'Rajesh Sharma'. Opening mortgage MORT-2931 on your screen now.
          - generic [ref=e40]:
            - generic [ref=e41]: "user:"
            - text: Prepare correction draft race
          - generic [ref=e42]:
            - generic [ref=e43]: "assistant:"
            - text: "Preparing a draft correction — I'll show the numbers on your screen.Draft correction for MORT-2931: effective 2025-01-01, projected EMI $2847.50 (delta $0.00). You can edit the effective date before we commit."
        - generic [ref=e44]:
          - textbox "Try \"Find Rajesh Sharma\"" [ref=e45]
          - button "Send" [disabled]
  - button "Open Next.js Dev Tools" [ref=e51] [cursor=pointer]
  - alert [ref=e55]
```

# Test source

```ts
  1   | import { expect, test } from "@playwright/test";
  2   | 
  3   | async function connectSession(page: import("@playwright/test").Page) {
  4   |   await page.goto("http://localhost:3000");
  5   |   await page.getByRole("button", { name: "Connect", exact: true }).click();
  6   |   await expect(page.getByText("RP:")).toContainText("ready", { timeout: 15_000 });
  7   |   await expect(page.getByText("Session ready.")).toBeVisible({ timeout: 15_000 });
  8   |   await page.evaluate(() => {
  9   |     (window as Window & { __relayConflictCount?: number }).__relayConflictCount = 0;
  10  |   });
  11  | }
  12  | 
  13  | async function openRajeshCase(page: import("@playwright/test").Page) {
  14  |   await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Find Rajesh Sharma");
  15  |   await page.getByRole("button", { name: "Send", exact: true }).click();
  16  |   await expect(page.getByTestId("mortgage-case-view")).toBeVisible({ timeout: 30_000 });
  17  | }
  18  | 
  19  | /** Edit effective date during prepare_correction race window (1.5s server-side). */
  20  | async function editEffectiveDateDuringSlowPrepare(
  21  |   page: import("@playwright/test").Page,
  22  |   effectiveDate: string,
  23  | ) {
  24  |   await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Prepare correction draft race");
  25  |   const dateInput = page.getByTestId("correction-effective-date");
  26  |   const fillDuringSlow = (async () => {
  27  |     await expect(page.getByTestId("correction-draft-view")).toBeVisible({ timeout: 12_000 });
  28  |     const deadline = Date.now() + 10_000;
  29  |     while (Date.now() < deadline) {
  30  |       if (await dateInput.isVisible()) {
  31  |         await dateInput.fill(effectiveDate);
  32  |         await dateInput.dispatchEvent("change");
  33  |         await dateInput.press("Tab");
  34  |         return;
  35  |       }
  36  |       await page.waitForTimeout(25);
  37  |     }
  38  |     throw new Error("correction-effective-date never became visible during slow prepare");
  39  |   })();
  40  |   await page.getByRole("button", { name: "Send", exact: true }).click();
  41  |   await fillDuringSlow;
  42  | }
  43  | 
  44  | const INTERNAL_LEAK_PATTERN =
  45  |   /routed handler|apply_state_delta|state_conflict|sync the ui|can't sync|cannot sync/i;
  46  | 
  47  | async function expectNoAssistantInternalLeak(page: import("@playwright/test").Page) {
  48  |   const assistants = page.locator('[data-testid="chat-message"][data-chat-role="assistant"]');
  49  |   const count = await assistants.count();
  50  |   for (let i = 0; i < count; i++) {
  51  |     const text = (await assistants.nth(i).textContent()) ?? "";
  52  |     expect(text).not.toMatch(INTERNAL_LEAK_PATTERN);
  53  |   }
  54  | }
  55  | 
  56  | async function expectConflictSignal(page: import("@playwright/test").Page) {
  57  |   await expect
  58  |     .poll(
  59  |       async () => page.evaluate(() => (window as Window & { __relayConflictCount?: number }).__relayConflictCount ?? 0),
  60  |       { timeout: 45_000 },
  61  |     )
> 62  |     .toBeGreaterThan(0);
      |      ^ Error: expect(received).toBeGreaterThan(expected)
  63  |   await expect(page.getByTestId("state-conflict-banner")).toBeVisible({ timeout: 5_000 });
  64  | }
  65  | 
  66  | /**
  67  |  * P08-TC-001–003 — draft correction, human edit during slow tool, post-conflict recompute.
  68  |  * Requires gateway @ :8080 and `pnpm dev` @ :3000.
  69  |  */
  70  | test.describe("Phase 8 state versioning", () => {
  71  |   test.skip(!process.env.PLAYWRIGHT_E2E, "set PLAYWRIGHT_E2E=1 with stack running");
  72  | 
  73  |   test("P08-TC-001b agent text date update syncs draft field", async ({ page }) => {
  74  |     await connectSession(page);
  75  |     await openRajeshCase(page);
  76  | 
  77  |     await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Prepare correction draft");
  78  |     await page.getByRole("button", { name: "Send", exact: true }).click();
  79  |     await expect(page.getByTestId("correction-draft-view")).toBeVisible({ timeout: 30_000 });
  80  | 
  81  |     await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("change the date to 01/01/2026");
  82  |     await page.getByRole("button", { name: "Send", exact: true }).click();
  83  |     await expect(page.getByTestId("correction-effective-date")).toHaveValue("2026-01-01", {
  84  |       timeout: 30_000,
  85  |     });
  86  |   });
  87  | 
  88  |   test("P08-TC-001 edit draft effective date bumps version and EMI", async ({ page }) => {
  89  |     await connectSession(page);
  90  |     await openRajeshCase(page);
  91  | 
  92  |     await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Prepare correction draft");
  93  |     await page.getByRole("button", { name: "Send", exact: true }).click();
  94  |     await expect(page.getByTestId("correction-draft-view")).toBeVisible({ timeout: 30_000 });
  95  | 
  96  |     const dateInput = page.getByTestId("correction-effective-date");
  97  |     await dateInput.fill("2025-06-15");
  98  |     await expect(page.getByTestId("correction-projected-emi")).toContainText("$");
  99  |   });
  100 | 
  101 |   test("P08-TC-002 stale agent update shows conflict and keeps human date", async ({ page }) => {
  102 |     await connectSession(page);
  103 |     await openRajeshCase(page);
  104 | 
  105 |     await editEffectiveDateDuringSlowPrepare(page, "2025-08-01");
  106 |     await expectConflictSignal(page);
  107 |     await expect(page.getByTestId("correction-effective-date")).toHaveValue("2025-08-01");
  108 |   });
  109 | 
  110 |   test("P08-TC-003 post-conflict draft matches edited effective date", async ({ page }) => {
  111 |     await connectSession(page);
  112 |     await openRajeshCase(page);
  113 | 
  114 |     await editEffectiveDateDuringSlowPrepare(page, "2025-09-01");
  115 |     await expectConflictSignal(page);
  116 |     await expect(page.getByTestId("correction-effective-date")).toHaveValue("2025-09-01");
  117 |     await expect(page.getByTestId("correction-projected-emi")).toBeVisible();
  118 |     await expect(page.getByTestId("shared-state-panel")).toContainText("2025-09-01", {
  119 |       timeout: 15_000,
  120 |     });
  121 |   });
  122 | 
  123 |   /** UAT script row #11 / [UAT-006](plans/UAT_VOICE_SCRIPT.md#uat-006) — text path. */
  124 |   test("UAT-006 March phrase updates draft without internal leak", async ({ page }) => {
  125 |     await connectSession(page);
  126 |     await openRajeshCase(page);
  127 | 
  128 |     await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Prepare correction draft");
  129 |     await page.getByRole("button", { name: "Send", exact: true }).click();
  130 |     await expect(page.getByTestId("correction-draft-view")).toBeVisible({ timeout: 30_000 });
  131 |     await expect(page.getByTestId("correction-effective-date")).toHaveValue("2025-01-01", {
  132 |       timeout: 15_000,
  133 |     });
  134 | 
  135 |     await page
  136 |       .getByPlaceholder('Try "Find Rajesh Sharma"')
  137 |       .fill("Change it to March, not January.");
  138 |     await page.getByRole("button", { name: "Send", exact: true }).click();
  139 |     await expect(page.getByTestId("correction-effective-date")).toHaveValue("2025-03-01", {
  140 |       timeout: 30_000,
  141 |     });
  142 |     await expectNoAssistantInternalLeak(page);
  143 |   });
  144 | });
  145 | 
```