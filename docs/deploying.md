# Deploying Relay on a server

Everything on one Linux server with Docker: the gateway (hosted service for developers with the SDK
and `relay login`, plus the example agents), the five example tools services, the website with the
Experience Center and the five sandbox example apps. Caddy serves it all over HTTPS with
certificates it gets from Let's Encrypt.

| Address | Service (container) | |
|---|---|---|
| `https://<DOMAIN>` | `website` | Marketing site + Experience Center (`/try`); `www.` redirects here |
| `https://api.<DOMAIN>` | `gateway` | API, `relay login`, session WebSocket, voice, `/admin`, `/metrics` |
| `https://crm.<DOMAIN>`, `shop.`, `bus.`, `stays.`, `bank.` | `crm-web`, `shop-web`, `bus-web`, `stays-web`, `bank-web` | Example apps in sandbox mode, shown in the website's iframes |
| — | `postgres`, `redis`, `*-tools` | Internal only, no ports on the server |

Files: `infra/docker/docker-compose.prod.yml`, `infra/docker/Caddyfile`,
`infra/docker/Dockerfile.web` (one image per Next.js app), `infra/docker/.env.prod.example`, and
`infra/docker/prod.sh` (runs `docker compose` with the right files).

## 1. Server and DNS

- Ubuntu 24.04 (or any Linux with Docker Engine and the Compose plugin, 2.24 or newer).
- 4 vCPUs and 8 GB RAM. The gateway runs the voice models (Silero, Smart Turn), and building
  six Next.js apps needs memory. 30 GB of disk.
- Firewall / cloud security group: allow inbound TCP 22, 80 and 443, UDP 443 (HTTP/3), and TCP +
  UDP 3478 (voice relay). Port 80 must be open for Let's Encrypt. Only Caddy publishes ports;
  Docker-published ports skip `ufw`, so don't publish others.
- On the server's own firewall (`ufw`), also allow the voice relay ports the gateway sends audio to:
  `ufw allow 3478 && ufw allow 49152:49252/udp` (only the server's cloud firewall needs 3478 open
  to the internet; 49152–49252 are used between coturn and the gateway on the same machine).
- DNS: `A` (and `AAAA` if the server has IPv6) records for `<DOMAIN>`, `www`, `api`, `crm`,
  `shop`, `bus`, `stays`, `bank` and `turn` pointing at the server (a wildcard `*.<DOMAIN>`
  record plus one for `<DOMAIN>` covers them). Create them before the first start,
  or Caddy cannot get certificates (it retries on its own).

Install Docker: `curl -fsSL https://get.docker.com | sh`, then `sudo usermod -aG docker $USER`
and log in again.

## 2. Configure

```bash
git clone <your repo URL> relay && cd relay
cp infra/docker/.env.prod.example infra/docker/.env.prod
chmod 600 infra/docker/.env.prod
```

Fill in `infra/docker/.env.prod`:

| Variable | |
|---|---|
| `DOMAIN`, `ACME_EMAIL` | Your domain and the Let's Encrypt contact |
| `POSTGRES_PASSWORD`, `RELAY_SECRETS_KEY`, `RELAY_TURN_SECRET` | Random values: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`. Keep `RELAY_SECRETS_KEY` forever (it decrypts stored model keys) |
| `OPENAI_API_KEY` | Used by the example agents for every Experience Center visitor: give it a monthly spending cap at OpenAI |
| `DEEPGRAM_API_KEY` | Voice for every project (text works without it) |
| `RELAY_SIGNUP` + `RELAY_SIGNUP_ALLOWLIST` | `allowlist` with your own email (and your team's `@domain`), or `closed` |
| `RELAY_SMTP_*` | Confirmation and password-reset emails. Without SMTP they are written to the gateway log |
| `RELAY_ADMIN_TOKEN`, `RELAY_METRICS_TOKEN` | Optional: turn on `/admin` and `/metrics` with these bearer tokens |

The rest of the gateway's settings (database, Redis, tools URLs, `RELAY_PUBLIC_URL`, proxy headers)
are fixed in `docker-compose.prod.yml`. All gateway variables are described in
[operating-the-gateway.md](operating-the-gateway.md).

## 3. Start

```bash
infra/docker/prod.sh up -d --build      # first build takes a while (gateway image + six web apps)
infra/docker/prod.sh ps                 # all services "running", gateway and tools "healthy"
infra/docker/prod.sh logs -f gateway    # look for `agent <id> loaded … (<n> tools)` for each example
```

Check:

- `https://<DOMAIN>/try` shows the gallery; open an example and send a text message.
- `curl https://api.<DOMAIN>/health` answers; `curl -X POST https://api.<DOMAIN>/dev/sessions` is a `404`.
- Voice: press the mic in an example, from a laptop and from a phone on mobile data (see Voice below).

## 4. Developer accounts (`relay login`)

```bash
npx @sumukhj1219-wkt-org/relay-cli login --gateway https://api.<DOMAIN>
```

The browser opens the gateway's sign-in page; sign up with an allowlisted email and confirm it. The
CLI remembers the gateway for later commands (or set `RELAY_GATEWAY_URL`). From there the customer
path is the one in the SDK guide: `relay secrets set openai`, `relay agents push`, `relay keys create`.
Customers' tools services must be public HTTPS URLs: private and `http://` tools URLs are refused on
this stack.

## 5. Update

```bash
git pull
infra/docker/prod.sh up -d --build
```

Only images whose files changed are rebuilt. When an update changes the stack's network (as the
TURN relay did), run `infra/docker/prod.sh down` before `up -d --build`; data volumes are kept. After changing `DOMAIN` rebuild everything (the web apps
compile their addresses in). After editing `agents/*.yaml` run `infra/docker/prod.sh restart gateway`.

## 6. Data and backups

| Volume | Holds |
|---|---|
| `relay-prod_relay-pg-data` | Accounts, projects, keys (hashed), encrypted model keys, event log |
| `relay-prod_crm-data`, `_shop-data`, `_bus-data`, `_stays-data`, `_bank-data` | Example data and per-visitor sandboxes |
| `relay-prod_caddy-data` | Certificates |

Back up Postgres daily, and keep `infra/docker/.env.prod` (with `RELAY_SECRETS_KEY`) somewhere safe.
Without that key a restored database cannot decrypt stored model keys:

```bash
infra/docker/prod.sh exec -T postgres pg_dump -U relay relay | gzip > relay-$(date +%F).sql.gz
```

`infra/docker/prod.sh down` keeps all data; `down -v` deletes it.

## How the Experience Center works here

The example apps' servers start each visitor's session with `POST /dev/sessions` on
`http://gateway:8080`, inside the Docker network, and run on the gateway's own agents (`agents/*.yaml`).
Caddy answers `/dev/*` with `404` on the public address, so nobody on the
internet can start a keyless session or read a session timeline. Browsers reach the gateway only
through `api.<DOMAIN>` (WebSocket and voice, with the session's token).

Limits: each example app allows 20 session starts per visitor address per 10 minutes, and the
gateway has no per-session time or turn cap yet. The OpenAI spending cap is the real limit on cost.

## Voice (WebRTC)

The gateway runs inside Docker, behind NAT, so browsers usually cannot reach it directly over UDP.
The stack includes a TURN relay (`coturn`, host networking, port 3478): before voice starts, the SDK
asks the gateway for ICE servers (`GET /sessions/{id}/webrtc/ice-servers`) and gets STUN plus TURN
credentials that expire after an hour, signed with `RELAY_TURN_SECRET`. coturn relays only to the
gateway's fixed address (`172.31.240.10` on the stack's network), never to other hosts, and does not
relay TCP.

If voice fails with "ICE failed": check that TCP and UDP 3478 are open in the cloud firewall, that
`ufw` allows `49152:49252/udp`, and `infra/docker/prod.sh logs coturn` (each attempt logs an
allocation; `401` means the secret differs between coturn and the gateway, which both read
`RELAY_TURN_SECRET`). Networks that block everything but HTTPS would need TURN over TLS on 443,
which this stack does not include.

## What this stack does not cover yet

- TURN over TLS (port 443) for networks that allow only HTTPS.
- Several gateways: one gateway process serves all sessions.
- Monitoring: Prometheus and Grafana run only in the local observability stack
  (`docker-compose.observability.yml`); on this server, scrape `https://api.<DOMAIN>/metrics` with
  `RELAY_METRICS_TOKEN` from your own monitoring.
- Approvals use the proof-of-concept approver token (`RELAY_DEV_APPROVER_TOKEN`, default
  `dev-approver`, which the SDK sends by default).
