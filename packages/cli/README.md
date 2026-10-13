# @sumukhj1219-wkt-org/relay-cli

`relay` — sign in to Relay and manage projects, API keys, agents and secrets.

```bash
npm install -g @sumukhj1219-wkt-org/relay-cli     # or: npx @sumukhj1219-wkt-org/relay-cli login
```

```bash
relay login                                  # opens the browser; saves an account token
relay whoami
relay keys create --kind publishable         # rpk_… for the browser SDK (shown once)
relay keys create --kind secret --name api   # rsk_… for your server only
relay origins set https://app.example.com    # pages allowed to use the publishable key
relay keys list
relay keys revoke <key-id>
relay projects create "Staging" && relay projects use <project-id>
relay logout

relay secrets set openai                     # paste your OpenAI key (hidden); or pipe it on stdin
relay agents push orders.yaml                # your agent: manifest + prompt + tools URL
relay agents list
relay tools secret                           # verify Relay's calls in your tools service
```

Then in the app:

```ts
createRelaySession({ gatewayUrl, apiKey: "rpk_…", agentId: "sales-crm" })
```

- Until a hosted address exists the gateway defaults to `http://localhost:8080`; use `--gateway <url>` on `login` or `RELAY_GATEWAY_URL`.
- The account token is stored in `~/.config/relay/credentials.json` (mode `600`). `relay logout` revokes it on the server as well.
- `relay secrets set` never takes the key as an argument (it would land in shell history). In CI: `printf %s "$OPENAI_API_KEY" | relay secrets set openai`.
- CI: set `RELAY_TOKEN` (and `RELAY_PROJECT`) instead of logging in.
- Inside the Relay repo you can also run it as `node packages/cli/bin/relay.mjs …`.

No dependencies; needs Node 18.3+.
