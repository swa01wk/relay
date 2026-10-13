// Where `relay login` keeps the account token: one JSON file only the user can read.
import { chmodSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";

// Used until a hosted gateway address exists; override with --gateway or RELAY_GATEWAY_URL.
export const DEFAULT_GATEWAY = "http://localhost:8080";

export function credentialsPath(env = process.env) {
  const base = env.XDG_CONFIG_HOME || join(homedir(), ".config");
  return join(base, "relay", "credentials.json");
}

export function readCredentials(env = process.env) {
  // RELAY_TOKEN lets CI use an account token without a credentials file.
  if (env.RELAY_TOKEN) {
    return { token: env.RELAY_TOKEN, gateway: gatewayUrl(undefined, env, null), project: env.RELAY_PROJECT };
  }
  const path = credentialsPath(env);
  if (!existsSync(path)) return null;
  try {
    const saved = JSON.parse(readFileSync(path, "utf8"));
    return typeof saved?.token === "string" ? saved : null;
  } catch {
    return null;
  }
}

export function writeCredentials(credentials, env = process.env) {
  const path = credentialsPath(env);
  mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
  writeFileSync(path, `${JSON.stringify(credentials, null, 2)}\n`, { mode: 0o600 });
  chmodSync(path, 0o600); // the mode above is ignored when the file already exists
  return path;
}

export function clearCredentials(env = process.env) {
  rmSync(credentialsPath(env), { force: true });
}

export function gatewayUrl(flag, env = process.env, saved = readCredentials(env)) {
  return (flag || env.RELAY_GATEWAY_URL || saved?.gateway || DEFAULT_GATEWAY).replace(/\/+$/, "");
}
