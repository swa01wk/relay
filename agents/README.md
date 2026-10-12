# Agent manifests

Each `*.yaml` here is a Relay agent the gateway loads at startup (`RELAY_AGENTS_DIR`, mounted at `/app/agents` in Docker). No Python needed: a manifest names the agent, points at a tools service and gives the system prompt.

| Key | Required | Meaning |
|---|---|---|
| `agent_id` | yes | What frontends pass as `agentId` |
| `tools_url` | yes | Tools service base URL; must serve `GET /tools` and `POST /tools/{name}`. `${VAR}` / `${VAR:-default}` expand from the environment |
| `system_prompt` / `system_prompt_file` | one of them | Who the assistant is and how it answers (file path is relative to the manifest) |
| `instructions` | no | Extra hints for rendering results (tables, charts, forms) |
| `tool_timeout_seconds` | no | Per tool call, default 30 |

Restart the gateway after adding or editing a manifest. A manifest that fails to load (bad YAML, unreachable tools service, duplicate `agent_id`) is skipped and logged as `agent manifest skipped: …`.
