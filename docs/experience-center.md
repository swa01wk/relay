# Experience Center: the website and example sandboxes

The marketing site (`apps/website`, Next.js 16, port 3003) has a public **Experience Center**
(`/try`) where visitors use the example apps live, embedded in an iframe. Every visitor works on
a **private copy of the demo data**, so one visitor's changes never show up for another.

## How a sandbox works

```
browser ──POST /api/assistant/session──▶ example app's server ──POST /v1/sessions {user: sandbox_…}──▶ gateway
   │        (sets HttpOnly cookie relay_sandbox)                     (secret key; /dev/sessions locally)
   └──── WebSocket / WebRTC with the returned session id + token ──────────────────────────▶ gateway
                                                                       gateway ──X-Relay-User──▶ tools service
                                                                                 (signed)        └ data for that sandbox
```

1. The example app's server (`examples/shared/sandbox`, used by two route handlers in each app)
   gives the visitor a random id (`sandbox_<32 hex>`) in an HttpOnly cookie that lasts 2 hours.
2. It starts the Relay session itself, for `user = { id: "sandbox_…" }`, and hands the browser only
   the session id and token. The browser can never pick the user id.
3. Relay sends that user to the tools service on every call (`X-Relay-User`, covered by the v2
   signature). The tools service keeps one dataset per sandbox id:
   - CRM: one SQLite file per sandbox in `CRM_SANDBOX_DIR`, copied from the seed on first use.
   - Mortgage: an in-memory copy of the seed per sandbox (`MORTGAGE_SANDBOXES=1`).
   - Storefront: one SQLite file per sandbox in `SHOP_SANDBOX_DIR`. The store already has per-shopper
     data, so the sandbox id simply *is* the shopper: `proxy.ts` sets the cookie before the first page
     renders, and the store's own API receives it as `X-Shop-User`.
   - Bus booking: the same as the storefront, with `BUS_SANDBOX_DIR` and `X-Bus-User`.
   - Rentals: the same, with `STAYS_SANDBOX_DIR` and `X-Stays-User`.
   Sandboxes idle for 2 h are deleted, and each service keeps at most 500
   (`CRM_SANDBOX_TTL_SECONDS` / `CRM_SANDBOX_MAX`, `MORTGAGE_SANDBOX_TTL_SECONDS` / `MORTGAGE_SANDBOX_MAX`).
4. **Reset demo** in the app calls `POST /api/sandbox/reset`, which calls the tools service's
   `POST /sandbox/reset` with `X-Sandbox-Id`, then opens a new conversation.

Requests without a sandbox id use the shared data, so the apps behave as before when sandbox
mode is off.

## Run it locally

```bash
docker compose -f infra/docker/docker-compose.yml up -d --build gateway crm-tools mortgage-tools shop-tools bus-tools stays-tools
pnpm install
pnpm --filter @relay/crm-frontend dev:sandbox        # :3002, sandbox mode, framable by :3003
pnpm --filter @relay/mortgage-frontend dev:sandbox   # :3000
pnpm --filter @relay/storefront-frontend dev:sandbox # :3004
pnpm --filter @relay/bus-frontend dev:sandbox        # :3005
pnpm --filter @relay/stays-frontend dev:sandbox      # :3006
pnpm --filter @relay/website dev                     # http://localhost:3003 → Experience Center
```

Locally the example apps use dev sessions (`RELAY_DEV_SESSIONS=1`, which accept `user`), so no
`relay login` is needed.

## Settings

| Where | Variable | Meaning |
|---|---|---|
| example app | `NEXT_PUBLIC_RELAY_SANDBOX=1` | Sandbox mode: sessions come from the app's server, Reset demo appears |
| example app | `RELAY_SECRET_KEY` | Demo project's secret key (`rsk_…`). **Required on a hosted gateway** (dev sessions are off there) |
| example app | `RELAY_GATEWAY_URL` | Gateway as the app's server reaches it (defaults to `NEXT_PUBLIC_GATEWAY_URL`) |
| example app | `RELAY_SANDBOX_FRAME_ANCESTORS` | Origins allowed to frame the app (`frame-ancestors`), e.g. the website's origin |
| example app | `CRM_TOOLS_URL` / `MORTGAGE_TOOLS_URL` | Tools service, for reset (and the CRM dashboard) |
| tools service | `CRM_SANDBOX_DIR` / `MORTGAGE_SANDBOXES=1` / `SHOP_SANDBOX_DIR` / `BUS_SANDBOX_DIR` / `STAYS_SANDBOX_DIR` | Turns per-visitor data on |
| website | `NEXT_PUBLIC_EXAMPLE_SALES_CRM_URL`, `NEXT_PUBLIC_EXAMPLE_MORTGAGE_URL`, `NEXT_PUBLIC_EXAMPLE_STOREFRONT_URL`, `NEXT_PUBLIC_EXAMPLE_BUS_BOOKING_URL`, `NEXT_PUBLIC_EXAMPLE_STAYS_URL` | Where each example runs |

Abuse and cost limits: the example's server allows 20 session starts per address per 10 minutes
(behind a proxy it reads `X-Forwarded-For`, so put it behind one that sets that header); the gateway
adds its own limits per key and per end user (30 sessions a minute). Each sandbox session uses the
demo project's model key, so give that project its own key with a spending cap at the provider.
There is no per-session time or turn cap on the gateway yet.

Iframes: over HTTPS the sandbox cookie is `SameSite=None; Secure; Partitioned`, so it works when
the website and the examples are on different sites. Over plain HTTP (localhost) it is `Lax`,
which works because all localhost ports count as one site.

On a server, [deploying.md](deploying.md) runs all of this behind Caddy: the example apps reach the
gateway inside the Docker network and `/dev/*` is not exposed.

## Add an example

1. Build the example as usual (`examples/<name>/frontend`, `tools`, an agent manifest).
2. Tools service: route data access through a per-sandbox store keyed on the `X-Relay-User` id
   (`sandbox_` prefix; copy `examples/sales-crm/tools/src/crm_tools_api/sandbox.py` or the mortgage
   one) and add `POST /sandbox/reset` (header `X-Sandbox-Id`).
3. Frontend: depend on `@relay/example-sandbox`, add `lib/sandbox.ts` +
   `app/api/assistant/session/route.ts` + `app/api/sandbox/reset/route.ts` (copy the CRM ones), and
   when `NEXT_PUBLIC_RELAY_SANDBOX=1` connect with the server's `sessionId` + token and show Reset
   demo. A session your server started does not deliver `SESSION_READY` to the browser: do what
   you did on it after `connect()` resolves. Add `transpilePackages`, the `frame-ancestors`
   header and the `output` switch (`RELAY_NEXT_STANDALONE`, used by the Docker image) to
   `next.config.ts`, and a `dev:sandbox` script.
4. Website: add an entry to `apps/website/lib/examples.ts` with its own
   `NEXT_PUBLIC_EXAMPLE_<NAME>_URL`. The gallery, sandbox page and home page pick it up.
5. Add the tools service to `services/gateway/tests/test_example_sandboxes.py` (or its own test file,
   like `test_storefront_tools.py`).
6. Server: add its tools service and a `<name>-web` service to `infra/docker/docker-compose.prod.yml`
   (copy `stays-web`), a site to `infra/docker/Caddyfile`, a DNS record, and its
   `NEXT_PUBLIC_EXAMPLE_<NAME>_URL` build arg on the `website` service ([deploying.md](deploying.md)).

An app with per-user data (like the storefront) can skip the cookie-on-first-session step: set the
cookie in `proxy.ts` (`newSandboxId` + `sandboxCookie` from `@relay/example-sandbox`) and use the
sandbox id as the signed-in user everywhere.
