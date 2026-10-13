import assert from "node:assert/strict";
import { mkdtempSync, statSync, writeFileSync } from "node:fs";
import { Readable } from "node:stream";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { main, readManifest, readSecret } from "./cli.mjs";
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
