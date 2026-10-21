import assert from "node:assert/strict";
import { mkdtempSync, statSync, writeFileSync } from "node:fs";
import { Readable } from "node:stream";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { createServer } from "node:http";

import { authed, main, readManifest, readSecret } from "./cli.mjs";
import { clearCredentials, credentialsPath, gatewayUrl, readCredentials, writeCredentials } from "./config.mjs";

function capture() {
  const lines = [];
  return { lines, log: (m) => lines.push(String(m)), error: (m) => lines.push(String(m)) };
}

test("credentials file is private and round-trips", () => {
  const env = { XDG_CONFIG_HOME: mkdtempSync(join(tmpdir(), "relay-cli-")) };
  assert.equal(readCredentials(env), null);
  const path = writeCredentials({ gateway: "http://g", token: "rat_x", project: "proj_1" }, env);
  assert.equal(path, credentialsPath(env));
  assert.equal(statSync(path).mode & 0o777, 0o600);
  assert.equal(readCredentials(env).token, "rat_x");
  writeCredentials({ gateway: "http://g", token: "rat_y" }, env); // overwrite keeps it private
  assert.equal(statSync(path).mode & 0o777, 0o600);
  clearCredentials(env);
  assert.equal(readCredentials(env), null);
});

test("gateway address: flag, then environment, then saved login, then default", () => {
  const saved = { gateway: "http://saved" };
  assert.equal(gatewayUrl("http://flag/", { RELAY_GATEWAY_URL: "http://env" }, saved), "http://flag");
  assert.equal(gatewayUrl(undefined, { RELAY_GATEWAY_URL: "http://env" }, saved), "http://env");
  assert.equal(gatewayUrl(undefined, {}, saved), "http://saved");
  assert.equal(gatewayUrl(undefined, {}, null), "http://localhost:8080");
  assert.equal(readCredentials({ RELAY_TOKEN: "rat_ci", RELAY_PROJECT: "proj_ci" }).project, "proj_ci");
});

test("help, unknown commands and signed-out commands", async () => {
  process.env.XDG_CONFIG_HOME = mkdtempSync(join(tmpdir(), "relay-cli-"));
  delete process.env.RELAY_TOKEN;
  let out = capture();
  assert.equal(await main(["help"], out), 0);
  assert.match(out.lines.join("\n"), /relay login/);
  out = capture();
  assert.equal(await main(["frobnicate"], out), 2);
  out = capture();
  assert.equal(await main(["--bogus"], out), 2);
  out = capture();
  assert.equal(await main(["keys", "list"], out), 1);
  assert.match(out.lines.join("\n"), /relay login/);
});

test("manifests carry their prompt file; secrets come from stdin, never arguments", async () => {
  const dir = mkdtempSync(join(tmpdir(), "relay-cli-"));
  writeFileSync(join(dir, "prompt.md"), "You help with orders.\n");
  writeFileSync(join(dir, "agent.yaml"), 'agent_id: orders\ntools_url: https://tools.example.com\nsystem_prompt_file: "prompt.md"\n');
  writeFileSync(join(dir, "inline.yaml"), "agent_id: a\ntools_url: https://t.example.com\nsystem_prompt: hi\n");
  assert.equal(readManifest(join(dir, "agent.yaml")).system_prompt, "You help with orders.\n");
  assert.equal(readManifest(join(dir, "inline.yaml")).system_prompt, null);
  assert.throws(() => readManifest(join(dir, "missing.yaml")), /no such file/);

  assert.equal(await readSecret("", Readable.from(["sk-piped-key\n"])), "sk-piped-key");

  process.env.XDG_CONFIG_HOME = mkdtempSync(join(tmpdir(), "relay-cli-"));
  process.env.RELAY_TOKEN = "rat_test";
  process.env.RELAY_PROJECT = "proj_test";
  const lines = [];
  const out = { log: (m) => lines.push(String(m)), error: (m) => lines.push(String(m)) };
  assert.equal(await main(["secrets", "set", "openai", "sk-on-the-command-line"], out), 1);
  assert.match(lines.join("\n"), /do not pass the key as an argument/);
  delete process.env.RELAY_TOKEN;
  delete process.env.RELAY_PROJECT;
});

test("a change the gateway wants confirmed asks for the password once, then retries", async () => {
  const seen = [];
  let confirmed = false;
  const server = createServer((req, res) => {
    let body = "";
    req.on("data", (c) => (body += c));
    req.on("end", () => {
      seen.push(`${req.method} ${req.url} ${req.headers.authorization}`);
      if (req.url === "/v1/auth/reauth") {
        confirmed = JSON.parse(body).password === "the password";
        res.writeHead(confirmed ? 200 : 401, { "content-type": "application/json" });
        return res.end(JSON.stringify(confirmed ? { status: "ok" } : { detail: "wrong password" }));
      }
      if (!confirmed) {
        res.writeHead(403, { "content-type": "application/json", "x-relay-reauth": "required" });
        return res.end(JSON.stringify({ detail: "enter your password to confirm this change" }));
      }
      res.writeHead(201, { "content-type": "application/json" });
      res.end(JSON.stringify({ key: "rsk_new" }));
    });
  });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const saved = { gateway: `http://127.0.0.1:${server.address().port}`, token: "rat_x" };
  try {
    const prompts = [];
    const created = await authed(saved, "/v1/projects/p/keys", { method: "POST", body: {} }, async (p) => {
      prompts.push(p);
      return "the password";
    });
    assert.deepEqual(created, { key: "rsk_new" });
    assert.equal(prompts.length, 1);
    assert.deepEqual(seen, [
      "POST /v1/projects/p/keys Bearer rat_x",
      "POST /v1/auth/reauth Bearer rat_x",
      "POST /v1/projects/p/keys Bearer rat_x",
    ]);
    // Plain errors are not retried and never prompt.
    confirmed = false;
    await assert.rejects(authed(saved, "/v1/projects/p/keys", { method: "POST", body: {} }, async () => "nope"), /wrong password/);
  } finally {
    server.close();
  }
});

test("password reset works signed out and only points at the gateway's own page", async () => {
  process.env.XDG_CONFIG_HOME = mkdtempSync(join(tmpdir(), "relay-cli-"));
  delete process.env.RELAY_TOKEN;
  const lines = [];
  const out = { log: (m) => lines.push(String(m)), error: (m) => lines.push(String(m)) };
  assert.equal(await main(["password", "reset", "--gateway", "https://relay.example.com/", "--no-browser"], out), 0);
  assert.match(lines.join("\n"), /https:\/\/relay\.example\.com\/v1\/auth\/forgot-password/);
});

test("logs and usage read the project's activity and keep conversation text from driving the terminal", async () => {
  const seen = [];
  const replies = {
    "/v1/projects/proj_test/sessions?limit=20": {
      sessions: [{ session_id: "s-1", agent_id: "orders", started_at: "2026-10-21T10:02:00+00:00", turns: 2, errors: 1, ended: true, live: false }],
    },
    "/v1/projects/proj_test/sessions/s-1": {
      session_id: "s-1", agent_id: "orders", started_at: "2026-10-21T10:02:00+00:00", last_event_at: "2026-10-21T10:05:00+00:00", live: false,
      turns: [{ user_text: "orders?\u001b]52;c;evil\u0007", assistant_text: "You have one order.", tool_names: ["list_orders", "list_orders"] }],
      errors: [{ at: "2026-10-21T10:03:00+00:00", code: "tool_failed:list_orders", message: "503" }],
      approvals: [],
      usage: { model_calls: 2, total_tokens: 1234, cost_usd: 0.0012 },
    },
    "/v1/projects/proj_test/usage?days=3": {
      days: 3, truncated: false,
      total: { sessions: 1, turns: 2, errors: 1, model: { model_calls: 2, input_tokens: 1000, output_tokens: 234, total_tokens: 1234 } },
      by_day: [{ date: "2026-10-21", sessions: 1, turns: 2, errors: 1, model: { total_tokens: 1234 } }],
      by_agent: [{ agent_id: "orders", sessions: 1, model: { total_tokens: 1234 } }],
      tools: [{ name: "list_orders", calls: 2, failures: 1, avg_ms: 40.2, max_ms: 61 }],
    },
  };
  const server = createServer((req, res) => {
    seen.push(req.url);
    const body = replies[req.url];
    res.writeHead(body ? 200 : 404, { "content-type": "application/json" });
    res.end(JSON.stringify(body ?? { detail: "session not found" }));
  });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  process.env.XDG_CONFIG_HOME = mkdtempSync(join(tmpdir(), "relay-cli-"));
  process.env.RELAY_TOKEN = "rat_test";
  process.env.RELAY_PROJECT = "proj_test";
  process.env.RELAY_GATEWAY_URL = `http://127.0.0.1:${server.address().port}`;
  try {
    let out = capture();
    assert.equal(await main(["logs"], out), 0);
    assert.match(out.lines[0], /^s-1\s+orders\s+2026-10-21 10:02\s+2 turns\s+ended\s+1 error$/);

    out = capture();
    assert.equal(await main(["logs", "s-1"], out), 0);
    const text = out.lines.join("\n");
    assert.match(text, /user: {6}orders\?\]52;c;evil\n/);
    assert.ok(!/[\u0000-\u0008\u000b-\u001f\u007f]/.test(text.replaceAll("\n", "")));
    assert.match(text, /tools: {5}list_orders\n/);
    assert.match(text, /tool_failed:list_orders {2}503/);
    assert.match(text, /Model: 2 calls, 1,234 tokens · \$0\.0012/);

    out = capture();
    assert.equal(await main(["usage", "--days", "3"], out), 0);
    assert.match(out.lines.join("\n"), /Last 3 days: 1 sessions, 2 turns, 1 errors[\s\S]*list_orders\s+2 calls\s+1 failed {2}avg 40 ms, max 61 ms/);

    out = capture();
    assert.equal(await main(["logs", "missing"], out), 1);
    assert.match(out.lines.join("\n"), /session not found/);
    assert.equal(await main(["usage", "--days", "0"], capture()), 1);
  } finally {
    server.close();
    delete process.env.RELAY_TOKEN;
    delete process.env.RELAY_PROJECT;
    delete process.env.RELAY_GATEWAY_URL;
  }
});
