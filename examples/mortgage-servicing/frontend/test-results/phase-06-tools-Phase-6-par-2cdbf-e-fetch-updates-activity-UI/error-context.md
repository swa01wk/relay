# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: phase-06-tools.spec.ts >> Phase 6 parallel tools >> P06-TC-002 parallel payment and rate fetch updates activity UI
- Location: e2e/phase-06-tools.spec.ts:22:7

# Error details

```
Error: expect(received).toBe(expected) // Object.is equality

Expected: true
Received: false

Call Log:
- Timeout 30000ms exceeded while waiting on the predicate
```

# Page snapshot

```yaml
- generic [active] [ref=e1]:
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
          - code [ref=e15]: b6494986-e072-4970-a3ae-d8a20660bfff
        - generic [ref=e16]:
          - generic [ref=e17]:
            - paragraph [ref=e18]: Application view
            - generic [ref=e20]:
              - paragraph [ref=e21]: Case MORT-2931
              - paragraph [ref=e22]: Rajesh Sharma
              - paragraph [ref=e23]: 14 Oak Lane, Austin, TX
              - paragraph [ref=e24]: "Status: active"
          - generic [ref=e25]:
            - paragraph [ref=e26]: Agent activity (RP)
            - paragraph [ref=e27]: No in-flight tool activity.
          - generic [ref=e28]:
            - paragraph [ref=e29]: Shared state (RP)
            - generic [ref=e30]: "{ \"screen\": \"mortgage_case\", \"workflow\": \"case_review\", \"selected_entity\": { \"type\": \"mortgage\", \"id\": \"MORT-2931\" }, \"search_query\": \"Rajesh Sharma\", \"search_results\": [ { \"id\": \"CUST-1001\", \"name\": \"Rajesh Sharma\", \"email\": \"rajesh.sharma@example.com\", \"mortgages\": [ { \"id\": \"MORT-2931\", \"status\": \"active\", \"property\": \"14 Oak Lane, Austin, TX\", \"current_rate\": 6.125, \"emi\": 2847.5 }, { \"id\": \"MORT-1102\", \"status\": \"closed\", \"property\": \"2200 W 5th St, Austin, TX\", \"current_rate\": 4.875, \"emi\": 0 } ] } ], \"case_summary\": { \"id\": \"MORT-2931\", \"status\": \"active\", \"property\": \"14 Oak Lane, Austin, TX\", \"current_rate\": 6.125, \"emi\": 2847.5, \"customer_name\": \"Rajesh Sharma\", \"customer_id\": \"CUST-1001\" }, \"rate_history\": [], \"correction_draft\": null, \"activities\": [] }"
        - generic [ref=e31]:
          - generic [ref=e32]:
            - generic [ref=e33]: "system:"
            - text: Session ready.
          - generic [ref=e34]:
            - generic [ref=e35]: "user:"
            - text: Find Rajesh Sharma
          - generic [ref=e36]:
            - generic [ref=e37]: "assistant:"
            - text: I found 1 customer match for 'Rajesh Sharma'. Opening mortgage MORT-2931 on your screen now.
        - generic [ref=e38]:
          - textbox "Try \"Find Rajesh Sharma\"" [ref=e39]
          - button "Send" [disabled]
  - button "Open Next.js Dev Tools" [ref=e45] [cursor=pointer]
  - alert [ref=e49]
```

# Test source

```ts
  1  | import { expect } from "@playwright/test";
  2  | 
  3  | export async function connectSession(page: import("@playwright/test").Page) {
  4  |   await page.goto("http://localhost:3000");
  5  |   await page.getByRole("button", { name: "Connect", exact: true }).click();
  6  |   await expect(page.getByText("RP:")).toContainText("ready", { timeout: 15_000 });
  7  |   await expect(page.getByText("Session ready.")).toBeVisible({ timeout: 15_000 });
  8  | }
  9  | 
  10 | /** Wait for Rajesh case UI and for the opening turn to finish (WS user text is async). */
  11 | export async function openRajeshCase(page: import("@playwright/test").Page) {
  12 |   await page.getByPlaceholder('Try "Find Rajesh Sharma"').fill("Find Rajesh Sharma");
  13 |   await page.getByRole("button", { name: "Send", exact: true }).click();
  14 |   await expect(page.getByTestId("mortgage-case-view")).toBeVisible({ timeout: 30_000 });
  15 |   await expect
  16 |     .poll(async () => page.getByRole("button", { name: "Send", exact: true }).isEnabled(), {
  17 |       timeout: 30_000,
  18 |     })
> 19 |     .toBe(true);
     |      ^ Error: expect(received).toBe(expected) // Object.is equality
  20 | }
  21 | 
```