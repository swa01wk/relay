# Agent manifests

Each `*.yaml` here is a **gateway-wide** agent the gateway loads at startup (`RELAY_AGENTS_DIR`, mounted at `/app/agents` in Docker). These serve local dev sessions (`RELAY_DEV_SESSIONS=1`) and the example apps. No Python needed: a manifest names the agent, points at a tools service and gives the system prompt.

**Customers do not put files here.** A customer uploads the same kind of file to their own project with `relay agents push agent.yaml`; differences for an uploaded manifest: `tools_url` must be a literal public `https://` URL (no `${VAR}`), the CLI sends the prompt file's text, an optional `model:` picks the model, and changes apply on the next push — no restart. See `packages/web-sdk/docs/02-backend.md`.

| Key | Required | Meaning |
|---|---|---|
| `agent_id` | yes | What frontends pass as `agentId` |
| `tools_url` | yes | Tools service base URL; must serve `GET /tools` and `POST /tools/{name}`. `${VAR}` / `${VAR:-default}` expand from the environment |
| `system_prompt` / `system_prompt_file` | one of them | Who the assistant is and how it answers (file path is relative to the manifest) |
| `instructions` | no | Extra hints for rendering results (tables, charts, forms) |
| `tool_timeout_seconds` | no | Per tool call, default 30 |
| `keyterms` | no | Words voice recognition should listen for (names, products, jargon); up to 100 phrases of 50 characters. Passed to Deepgram as `keyterm` hints (nova-3 models) |

For files in this folder: restart the gateway after adding or editing a manifest. A manifest that fails to load (bad YAML, unreachable tools service, duplicate `agent_id`) is skipped and logged as `agent manifest skipped: …`.
