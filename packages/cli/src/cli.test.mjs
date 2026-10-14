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
