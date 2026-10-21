import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { hostname } from "node:os";
import { dirname, resolve } from "node:path";
import { parseArgs } from "node:util";

import { ApiError, request } from "./api.mjs";
import { clearCredentials, credentialsPath, gatewayUrl, readCredentials, writeCredentials } from "./config.mjs";

const HELP = `relay — Relay command line

Usage
  relay login [--gateway <url>] [--no-browser]   Sign in from the browser and save an account token
  relay logout [--all]                           Sign out this device (--all: every device)
  relay whoami                                   Show the signed-in account and its projects
  relay sessions                                 Devices signed in to your account
  relay sessions revoke <id>                     Sign a device out (e.g. a lost laptop)
  relay password                                 Change your password; signs out every other device
  relay password reset [--gateway <url>]         Forgot it? Opens the page that emails you a reset link

  relay projects list
  relay projects create <name>
  relay projects use <project-id>                Make a project the default for later commands

  relay keys list [--project <id>]
  relay keys create [--kind secret|publishable] [--name <label>] [--project <id>]
  relay keys revoke <key-id> [--project <id>]

  relay origins set <origin>... [--project <id>] Pages allowed to use the publishable key
  relay origins clear [--project <id>]

  relay agents push <agent.yaml> [--project <id>]  Create or update an agent from a manifest
  relay agents list [--project <id>]
  relay agents delete <agent-id> [--project <id>]

  relay secrets set openai [--project <id>]      Store your OpenAI API key (typed hidden, or piped on stdin)
  relay secrets list [--project <id>]
  relay secrets unset openai [--project <id>]

  relay tools secret [--rotate] [--project <id>] Signing secret your tools service verifies Relay's calls with

  relay logs [--limit <n>] [--project <id>]      Recent conversations with your assistant
  relay logs <session-id> [--project <id>]       One conversation: messages, tool calls, errors, tokens
  relay usage [--days <n>] [--project <id>]      Sessions, tokens, cost, errors and tool calls (default 7 days)
                                                 Add --json to logs or usage for the raw data

Keys
  publishable (rpk_…)  for the browser SDK: createRelaySession({ apiKey })
  secret (rsk_…)       for your server only; never ship it to a browser

Environment
  RELAY_GATEWAY_URL  gateway address    RELAY_TOKEN  account token (CI)    RELAY_PROJECT  default project
`;

const OPTIONS = {
  gateway: { type: "string" },
  project: { type: "string" },
  kind: { type: "string" },
  name: { type: "string" },
  "no-browser": { type: "boolean" },
  all: { type: "boolean" },
  rotate: { type: "boolean" },
  limit: { type: "string" },
  days: { type: "string" },
  json: { type: "boolean" },
  help: { type: "boolean", short: "h" },
};

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function openBrowser(url) {
  const [command, args] =
    process.platform === "darwin" ? ["open", [url]]
    : process.platform === "win32" ? ["cmd", ["/c", "start", "", url]]
    : ["xdg-open", [url]];
  try {
    const child = spawn(command, args, { stdio: "ignore", detached: true });
    child.on("error", () => {}); // no browser available: the URL is printed anyway
    child.unref();
  } catch {
    // ignore
  }
}

/**
 * A call made as the signed-in account. When the gateway asks for the password again
 * (changes that could hand the project to someone holding a copy of this token), prompt for it
 * once, confirm it, and retry.
 */
export async function authed(saved, path, options = {}, ask = readSecret) {
  const call = () => request(saved.gateway, path, { ...options, token: saved.token });
  try {
    return await call();
  } catch (error) {
    if (!(error instanceof ApiError) || !error.reauth) throw error;
    const password = await ask("Confirm with your Relay password (input hidden): ");
    if (!password) throw new Error("no password entered");
    await request(saved.gateway, "/v1/auth/reauth", { method: "POST", token: saved.token, body: { password } });
    return call();
  }
}

function signedIn(out) {
  const saved = readCredentials();
  if (!saved) {
    out.error("Not signed in. Run `relay login` first.");
    return null;
  }
  return saved;
}

function projectId(flags, saved) {
  const id = flags.project || process.env.RELAY_PROJECT || saved.project;
  if (!id) throw new Error("no project selected; pass --project <id> or run `relay projects use <id>`");
  return id;
}

async function login(flags, out) {
  const gateway = gatewayUrl(flags.gateway);
  const start = await request(gateway, "/v1/auth/device", { method: "POST" });
  out.log(`\nOpen this page to sign in:\n\n  ${start.verification_uri_complete}\n`);
  out.log(`and confirm the code  ${start.user_code}\n`);
  out.log("New to Relay? Tick “I'm new”; you will confirm your email before this terminal is signed in.\n");
  if (!flags["no-browser"]) openBrowser(start.verification_uri_complete);
  out.log("Waiting for approval…");

  const deadline = Date.now() + start.expires_in * 1000;
  while (Date.now() < deadline) {
    await sleep(start.interval * 1000);
    const poll = await request(gateway, "/v1/auth/device/token", {
      method: "POST",
      // Names this device in `relay sessions`, so a sign-in you don't recognise stands out.
      body: { device_code: start.device_code, client_name: `${hostname()} (${process.platform})` },
    });
    if (poll.status !== "approved") continue;
    const path = writeCredentials({ gateway, token: poll.token, email: poll.email, project: poll.project.id });
    out.log(`\nSigned in as ${poll.email}.`);
    out.log(`Default project: ${poll.project.name} (${poll.project.id})`);
    out.log(`Token saved to ${path}`);
    out.log("\nNext: relay keys create --kind publishable");
    return 0;
  }
  out.error("Login timed out. Run `relay login` again.");
  return 1;
}

async function logout(flags, out) {
  const saved = readCredentials();
  if (saved) {
    // Revoke server-side too; a stolen copy of the file stops working.
    await authed(saved, "/v1/auth/logout", { method: "POST", body: { everywhere: Boolean(flags.all) } }).catch(() => {});
  }
  clearCredentials();
  out.log(flags.all ? "Signed out on every device." : "Signed out.");
  return 0;
}

async function sessions(action, args, _flags, out) {
  const saved = signedIn(out);
  if (!saved) return 1;
  if (action === "list" || action === undefined) {
    const { sessions: list } = await authed(saved, "/v1/auth/sessions");
    for (const device of list) {
      const used = device.last_used_at ? `last used ${device.last_used_at.slice(0, 16).replace("T", " ")}` : "unused";
      out.log(`${device.current ? "*" : " "} ${device.id}  ${device.name}  ${used}${device.last_used_ip ? ` from ${device.last_used_ip}` : ""}`);
    }
    out.log("\nDon't recognise one? relay sessions revoke <id>, then relay password");
    return 0;
  }
  if (action === "revoke") {
    const [id] = args;
    if (!id) throw new Error("usage: relay sessions revoke <id>");
    await authed(saved, `/v1/auth/sessions/${encodeURIComponent(id)}`, { method: "DELETE" });
    out.log(`Signed out ${id}`);
    return 0;
  }
  throw new Error(`unknown command: relay sessions ${action}`);
}

async function password(action, flags, out) {
  if (action === "reset") {
    // Works signed out: the reset link goes to the account's email.
    const url = `${gatewayUrl(flags.gateway)}/v1/auth/forgot-password`;
    out.log(`Open this page and enter your email; we'll send a reset link:\n\n  ${url}\n`);
    if (!flags["no-browser"]) openBrowser(url);
    return 0;
  }
  if (action !== undefined) throw new Error(`unknown command: relay password ${action}`);
  const saved = signedIn(out);
  if (!saved) return 1;
  const current = await readSecret("Current password (input hidden): ");
  const next = await readSecret("New password, 10+ characters (input hidden): ");
  const again = await readSecret("New password again: ");
  if (next !== again) throw new Error("the new passwords do not match");
  const changed = await request(saved.gateway, "/v1/auth/password", {
    method: "POST",
    token: saved.token,
    body: { current_password: current, new_password: next },
  });
  out.log(`Password changed. Signed out ${changed.other_devices_signed_out} other device(s).`);
  return 0;
}

async function whoami(_flags, out) {
  const saved = signedIn(out);
  if (!saved) return 1;
  const me = await authed(saved, "/v1/me", {});
  out.log(`${me.email}  (${saved.gateway})`);
  for (const project of me.projects) {
    out.log(`  ${project.id === saved.project ? "*" : " "} ${project.id}  ${project.name}`);
  }
  return 0;
}

async function projects(action, args, _flags, out) {
  const saved = signedIn(out);
  if (!saved) return 1;
  if (action === "list" || action === undefined) {
    const { projects: list } = await authed(saved, "/v1/projects", {});
    for (const project of list) {
      out.log(`${project.id === saved.project ? "*" : " "} ${project.id}  ${project.name}`);
    }
    return 0;
  }
  if (action === "create") {
    const name = args.join(" ").trim();
    if (!name) throw new Error("usage: relay projects create <name>");
    const project = await authed(saved, "/v1/projects", { method: "POST", body: { name } });
    out.log(`Created ${project.name} (${project.id})`);
    return 0;
  }
  if (action === "use") {
    const [id] = args;
    const { projects: list } = await authed(saved, "/v1/projects", {});
    const project = list.find((p) => p.id === id);
    if (!project) throw new Error(`no project ${id ?? ""} in this account`.replace("  ", " "));
    writeCredentials({ ...saved, project: project.id });
    out.log(`Using ${project.name} (${project.id})`);
    return 0;
  }
  throw new Error(`unknown command: relay projects ${action}`);
}

async function keys(action, args, flags, out) {
  const saved = signedIn(out);
  if (!saved) return 1;
  const base = `/v1/projects/${encodeURIComponent(projectId(flags, saved))}/keys`;
  if (action === "list" || action === undefined) {
    const { keys: list } = await authed(saved, base, {});
    if (!list.length) out.log("No keys yet. Create one: relay keys create --kind publishable");
    for (const key of list) {
      const where = key.last_used_ip ? ` from ${key.last_used_ip}` : "";
      const spread = key.addresses_seen > 1 ? ` (${key.addresses_seen} addresses)` : "";
      const state = key.revoked ? "revoked" : key.last_used_at ? `used ${key.last_used_at.slice(0, 10)}${where}${spread}` : "unused";
      out.log(`${key.id}  ${key.kind.padEnd(11)}  ${key.prefix}…  ${state}  ${key.name}`);
    }
    return 0;
  }
  if (action === "create") {
    const kind = flags.kind ?? "publishable";
    const created = await authed(saved, base, {
      method: "POST",
      body: { kind, name: flags.name ?? "" },
    });
    out.log(`\n${created.key}\n`);
    out.log(`This ${kind} key is shown once — copy it now.`);
    out.log(
      kind === "secret"
        ? "Keep it on your server. Anyone holding it can start sessions billed to this project."
        : "Use it in the browser SDK: createRelaySession({ apiKey, agentId, gatewayUrl }).",
    );
    return 0;
  }
  if (action === "revoke") {
    const [id] = args;
    if (!id) throw new Error("usage: relay keys revoke <key-id>");
    await authed(saved, `${base}/${encodeURIComponent(id)}`, { method: "DELETE" });
    out.log(`Revoked ${id}`);
    return 0;
  }
  throw new Error(`unknown command: relay keys ${action}`);
}

async function origins(action, args, flags, out) {
  const saved = signedIn(out);
  if (!saved) return 1;
  if (action !== "set" && action !== "clear") throw new Error("usage: relay origins set <origin>... | relay origins clear");
  if (action === "set" && !args.length) throw new Error("usage: relay origins set https://app.example.com");
  const project = await authed(saved, `/v1/projects/${encodeURIComponent(projectId(flags, saved))}/origins`, {
    method: "PUT",
    body: { allowed_origins: action === "set" ? args : [] },
  });
  out.log(
    project.allowed_origins.length
      ? `Publishable keys for ${project.name} work only from: ${project.allowed_origins.join(", ")}`
      : `Publishable keys for ${project.name} work from any origin.`,
  );
  return 0;
}

/** Read a secret without showing it: hidden typing on a terminal, or the whole of piped stdin. */
export function readSecret(prompt, input = process.stdin, output = process.stderr) {
  if (!input.isTTY) {
    return new Promise((resolvePromise, reject) => {
      let data = "";
      input.setEncoding("utf8");
      input.on("data", (chunk) => (data += chunk));
      input.on("end", () => resolvePromise(data.trim()));
      input.on("error", reject);
    });
  }
  return new Promise((resolvePromise, reject) => {
    output.write(prompt);
    let value = "";
    input.setRawMode(true);
    input.resume();
    input.setEncoding("utf8");
    const finish = (error) => {
      input.setRawMode(false);
      input.pause();
      input.off("data", onData);
      output.write("\n");
      error ? reject(error) : resolvePromise(value.trim());
    };
    const onData = (chunk) => {
      for (const ch of chunk) {
        if (ch === "\r" || ch === "\n") return finish();
        if (ch === "\u0003") return finish(new Error("cancelled"));
        if (ch === "\u007f" || ch === "\b") value = value.slice(0, -1);
        else value += ch;
      }
    };
    input.on("data", onData);
  });
}

/** The manifest text plus, when it names a `system_prompt_file`, that file's content. */
export function readManifest(path) {
  if (!existsSync(path)) throw new Error(`no such file: ${path}`);
  const manifest = readFileSync(path, "utf8");
  const reference = manifest.match(/^system_prompt_file:[ \t]*(.+?)[ \t]*$/m);
  if (!reference) return { manifest, system_prompt: null };
  const promptPath = resolve(dirname(path), reference[1].replace(/^["']|["']$/g, ""));
  if (!existsSync(promptPath)) throw new Error(`system_prompt_file not found: ${promptPath}`);
  return { manifest, system_prompt: readFileSync(promptPath, "utf8") };
}

async function agents(action, args, flags, out) {
  const saved = signedIn(out);
  if (!saved) return 1;
  const base = `/v1/projects/${encodeURIComponent(projectId(flags, saved))}/agents`;
  if (action === "list" || action === undefined) {
    const { agents: list } = await authed(saved, base, {});
    if (!list.length) out.log("No agents yet. Add one: relay agents push agent.yaml");
    for (const agent of list) out.log(`${agent.agent_id}  ${agent.tools_url}  updated ${agent.updated_at.slice(0, 10)}`);
    return 0;
  }
  if (action === "push") {
    const [file] = args;
    if (!file) throw new Error("usage: relay agents push <agent.yaml>");
    const pushed = await authed(saved, base, { method: "POST", body: readManifest(file) });
    out.log(`Agent ${pushed.agent_id} is live (${pushed.tools.length} tools from ${pushed.tools_url}).`);
    if (pushed.tools.length) out.log(`Tools: ${pushed.tools.join(", ")}`);
    out.log(`Use it: createRelaySession({ apiKey, agentId: "${pushed.agent_id}", gatewayUrl })`);
    return 0;
  }
  if (action === "delete") {
    const [id] = args;
    if (!id) throw new Error("usage: relay agents delete <agent-id>");
    await authed(saved, `${base}/${encodeURIComponent(id)}`, { method: "DELETE" });
    out.log(`Deleted ${id}`);
    return 0;
  }
  throw new Error(`unknown command: relay agents ${action}`);
}

async function secrets(action, args, flags, out) {
  const saved = signedIn(out);
  if (!saved) return 1;
  const base = `/v1/projects/${encodeURIComponent(projectId(flags, saved))}/secrets`;
  if (action === "list" || action === undefined) {
    const { secrets: list } = await authed(saved, base, {});
    for (const secret of list) {
      out.log(`${secret.name.padEnd(8)} ${secret.set ? `set (${secret.hint}, ${secret.updated_at.slice(0, 10)})` : "not set"}`);
    }
    return 0;
  }
  const [name] = args;
  if ((action !== "set" && action !== "unset") || !name) throw new Error("usage: relay secrets set|unset openai");
  if (args.length > 1) {
    // A key on the command line ends up in shell history and process listings.
    throw new Error("do not pass the key as an argument; run `relay secrets set openai` and paste it when asked");
  }
  const path = `${base}/${encodeURIComponent(name)}`;
  if (action === "unset") {
    await authed(saved, path, { method: "DELETE" });
    out.log(`Removed ${name}.`);
    return 0;
  }
  const value = await readSecret(`Paste your ${name} API key (input hidden): `);
  if (!value) throw new Error("no key entered");
  const stored = await authed(saved, path, { method: "PUT", body: { value } });
  out.log(`Saved ${stored.name} key ${stored.hint}. It is stored encrypted and is never shown again.`);
  return 0;
}

async function tools(action, _args, flags, out) {
  const saved = signedIn(out);
  if (!saved) return 1;
  if (action !== "secret") throw new Error("usage: relay tools secret [--rotate]");
  const path = `/v1/projects/${encodeURIComponent(projectId(flags, saved))}/tools-signing-secret${flags.rotate ? "?rotate=true" : ""}`;
  const { signing_secret: secret } = await authed(saved, path, { method: "POST" });
  out.log(`\n${secret}\n`);
  out.log("Set this in your tools service and verify X-Relay-Signature on every request.");
  if (flags.rotate) out.log("The previous secret no longer works; update your tools service now.");
  return 0;
}

// Conversation text comes from end users and the model: never let it drive the terminal.
const clean = (text) => String(text ?? "").replace(/[\u0000-\u0008\u000b-\u001f\u007f-\u009f]/g, "");
const when = (iso) => (iso ? iso.slice(0, 16).replace("T", " ") : "?");
const number = (n) => Number(n ?? 0).toLocaleString("en-US");
const cost = (model) => (typeof model?.cost_usd === "number" ? ` · $${model.cost_usd.toFixed(4)}` : "");

function positiveInt(value, name, fallback) {
  if (value === undefined) return fallback;
  const n = Number(value);
  if (!Number.isInteger(n) || n < 1) throw new Error(`--${name} must be a positive whole number`);
  return n;
}

async function logs(sessionId, _args, flags, out) {
  const saved = signedIn(out);
  if (!saved) return 1;
  const base = `/v1/projects/${encodeURIComponent(projectId(flags, saved))}/sessions`;
  if (!sessionId) {
    const limit = positiveInt(flags.limit, "limit", 20);
    const { sessions: list } = await authed(saved, `${base}?limit=${limit}`, {});
    if (flags.json) {
      out.log(JSON.stringify(list, null, 2));
      return 0;
    }
    if (!list.length) out.log("No conversations yet.");
    for (const row of list) {
      const state = row.live ? "live" : row.ended ? "ended" : "idle";
      const errors = row.errors ? `  ${row.errors} error${row.errors === 1 ? "" : "s"}` : "";
      out.log(`${row.session_id}  ${clean(row.agent_id ?? "?").padEnd(16)}  ${when(row.started_at)}  ${String(row.turns).padStart(3)} turns  ${state}${errors}`);
    }
    if (list.length) out.log("\nOne conversation in full: relay logs <session-id>");
    return 0;
  }
  const detail = await authed(saved, `${base}/${encodeURIComponent(sessionId)}`, {});
  if (flags.json) {
    out.log(JSON.stringify(detail, null, 2));
    return 0;
  }
  out.log(`Session ${detail.session_id} · agent ${clean(detail.agent_id ?? "?")} · ${when(detail.started_at)} → ${when(detail.last_event_at)}${detail.live ? " (live)" : ""}`);
  detail.turns.forEach((turn, i) => {
    out.log(`\n#${i + 1}`);
    if (turn.user_text) out.log(`  user:      ${clean(turn.user_text)}`);
    if (turn.tool_names.length) out.log(`  tools:     ${[...new Set(turn.tool_names)].map(clean).join(", ")}`);
    if (turn.assistant_text) out.log(`  assistant: ${clean(turn.assistant_text)}`);
  });
  if (detail.errors.length) {
    out.log("\nErrors");
    for (const e of detail.errors) out.log(`  ${when(e.at)}  ${clean(e.code)}  ${clean(e.message)}`);
  }
  for (const a of detail.approvals) out.log(`\nApproval: ${clean(a.tool_name)} → ${clean(a.decision)}${a.outcome ? ` (${clean(a.outcome)})` : ""}`);
  const usage = detail.usage;
  out.log(`\nModel: ${number(usage.model_calls)} calls, ${number(usage.total_tokens)} tokens${cost(usage)}`);
  return 0;
}

async function usage(flags, out) {
  const saved = signedIn(out);
  if (!saved) return 1;
  const days = positiveInt(flags.days, "days", 7);
  const report = await authed(saved, `/v1/projects/${encodeURIComponent(projectId(flags, saved))}/usage?days=${days}`, {});
  if (flags.json) {
    out.log(JSON.stringify(report, null, 2));
    return 0;
  }
  const t = report.total;
  out.log(`Last ${report.days} day${report.days === 1 ? "" : "s"}: ${number(t.sessions)} sessions, ${number(t.turns)} turns, ${number(t.errors)} errors`);
  out.log(`Model: ${number(t.model.model_calls)} calls, ${number(t.model.total_tokens)} tokens (${number(t.model.input_tokens)} in, ${number(t.model.output_tokens)} out)${cost(t.model)}`);
  if (report.truncated) out.log("(busy period: only the most recent events are counted; use fewer --days)");
  if (report.by_day.length) {
    out.log("\nBy day (UTC)");
    for (const d of report.by_day) {
      out.log(`  ${d.date}  ${String(d.sessions).padStart(5)} sessions  ${String(d.turns).padStart(5)} turns  ${String(d.errors).padStart(3)} errors  ${number(d.model.total_tokens).padStart(10)} tokens${cost(d.model)}`);
    }
  }
  if (report.by_agent.length) {
    out.log("\nBy agent");
    for (const a of report.by_agent) {
      out.log(`  ${clean(a.agent_id ?? "(started earlier)").padEnd(18)}  ${String(a.sessions).padStart(5)} sessions  ${number(a.model.total_tokens).padStart(10)} tokens${cost(a.model)}`);
    }
  }
  if (report.tools.length) {
    out.log("\nTools");
    for (const tool of report.tools) {
      const timing = tool.avg_ms === null ? "" : `  avg ${Math.round(tool.avg_ms)} ms, max ${Math.round(tool.max_ms)} ms`;
      out.log(`  ${clean(tool.name).padEnd(24)}  ${String(tool.calls).padStart(5)} calls  ${String(tool.failures).padStart(3)} failed${timing}`);
    }
  }
  return 0;
}

export async function main(argv, out = console) {
  let parsed;
  try {
    parsed = parseArgs({ args: argv, options: OPTIONS, allowPositionals: true });
  } catch (error) {
    out.error(`relay: ${error.message}\nRun \`relay help\` for usage.`);
    return 2;
  }
  const { values: flags, positionals } = parsed;
  const [command, action, ...rest] = positionals;
  if (flags.help || !command || command === "help") {
    out.log(HELP);
    return 0;
  }
  try {
    switch (command) {
      case "login":
        return await login(flags, out);
      case "logout":
        return await logout(flags, out);
      case "whoami":
        return await whoami(flags, out);
      case "sessions":
        return await sessions(action, rest, flags, out);
      case "password":
        return await password(action, flags, out);
      case "projects":
        return await projects(action, rest, flags, out);
      case "keys":
        return await keys(action, rest, flags, out);
      case "origins":
        return await origins(action, rest, flags, out);
      case "agents":
        return await agents(action, rest, flags, out);
      case "secrets":
        return await secrets(action, rest, flags, out);
      case "tools":
        return await tools(action, rest, flags, out);
      case "logs":
        return await logs(action, rest, flags, out);
      case "usage":
        return await usage(flags, out);
      default:
        out.error(`relay: unknown command "${command}"\nRun \`relay help\` for usage.`);
        return 2;
    }
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      out.error(`relay: ${error.message}. Run \`relay login\` again.`);
      return 1;
    }
    if (error instanceof ApiError && error.status === 429) {
      out.error(`relay: ${error.message}`);
      return 1;
    }
    out.error(`relay: ${error.message}`);
    return 1;
  }
}

export { credentialsPath };
