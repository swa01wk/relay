# @sumukhj1219-wkt-org/relay-cli

`relay` — sign in to Relay and manage projects, API keys, agents and secrets.

```bash
npm install -g @sumukhj1219-wkt-org/relay-cli     # or: npx @sumukhj1219-wkt-org/relay-cli login
```

```bash
relay init                                   # in your app's folder: points Claude Code, Cursor, Codex at the SDK docs
relay login                                  # opens the browser (new accounts confirm their email first)
relay whoami
relay keys create --kind publishable         # rpk_… for the browser SDK (shown once)
relay keys create --kind secret --name api   # rsk_… for your server only
relay origins set https://app.example.com    # pages allowed to use the publishable key
relay keys list
relay keys revoke <key-id>
relay projects create "Staging" && relay projects use <project-id>
relay sessions                               # devices signed in to your account
relay sessions revoke <id>                   # sign out a lost or unknown device
relay password                               # change password; signs out every other device
relay password reset                         # forgot it: emails you a reset link
relay logout                                 # this device (--all: every device)

relay secrets set openai                     # paste your OpenAI key (hidden); or pipe it on stdin
relay agents push orders.yaml                # your agent: manifest + prompt + tools URL
relay agents list
relay tools secret                           # verify Relay's calls in your tools service

relay logs                                   # recent conversations with your assistant
relay logs <session-id>                      # one conversation: messages, tools, errors, approvals, tokens
relay usage --days 30                        # sessions, tokens, cost, errors per day/agent; calls and timing per tool
relay usage --json                           # raw data for your own dashboards
```

Then in the app:

```ts
createRelaySession({ gatewayUrl, apiKey: "rpk_…", agentId: "sales-crm" })
```

- `relay init` needs no sign-in. It adds a marked block to `AGENTS.md` and `CLAUDE.md` (your own text is kept; re-running replaces only the block) and writes `.cursor/rules/relay.mdc`, all pointing at the installed SDK's docs (found in `node_modules`, also a workspace root's). Commit them. `--dir <path>` targets another folder.
- Until a hosted address exists the gateway defaults to `http://localhost:8080`; use `--gateway <url>` on `login` or `RELAY_GATEWAY_URL`.
- The account token is stored in `~/.config/relay/credentials.json` (mode `600`), one per device. It expires after 30 days (14 unused). `relay logout` revokes it on the server as well.
- Someone with a copy of that file still cannot create keys, change your model key or agents, or reveal the signing secret: those changes ask for your password (the CLI prompts and retries). If a device is lost: `relay sessions revoke <id>`, then `relay password`.
- `relay secrets set` never takes the key as an argument (it would land in shell history). In CI: `printf %s "$OPENAI_API_KEY" | relay secrets set openai`.
- CI: set `RELAY_TOKEN` (and `RELAY_PROJECT`) instead of logging in.
- Inside the Relay repo you can also run it as `node packages/cli/bin/relay.mjs …`.

No dependencies; needs Node 18.3+.
