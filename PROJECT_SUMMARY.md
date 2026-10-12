# Recent Updates

This repo has moved from a basic chat/session prototype into a structured AI UI runtime.

## What changed

- Added generative UI support in the runtime and Web SDK via `present_ui`-style surface payloads and form submissions.
- Expanded the frontend playground to render structured surfaces: tables, charts, cards, comparison views, notices, markdown, and forms.
- Hardened session handling around state sync, event persistence, and conflict resolution.
- Improved tool orchestration and model integration for mortgage workflows, including read-only tools and approval-driven actions.
- Added tests covering routing, generative UI, session cleanup, and gateway state conflict handling.

## SDK / UI changes

- [packages/web-sdk/src/ui-surfaces.ts](packages/web-sdk/src/ui-surfaces.ts) now normalizes and types UI surfaces for client rendering.
- [packages/web-sdk/src/index.ts](packages/web-sdk/src/index.ts) includes the session API for actions, state, approvals, and app events.
- [examples/mortgage-servicing/frontend/src/app/page.tsx](examples/mortgage-servicing/frontend/src/app/page.tsx) shows the app using live session state + surface rendering.
- [examples/mortgage-servicing/frontend/src/components/playground-canvas.tsx](examples/mortgage-servicing/frontend/src/components/playground-canvas.tsx) and [examples/mortgage-servicing/frontend/src/components/playground-chart.tsx](examples/mortgage-servicing/frontend/src/components/playground-chart.tsx) handle the actual UI rendering.

## Where it is heading

The direction is clear: make Relay a reusable real-time agent platform where the model can produce both conversational responses and structured UI, while the app owns the final presentation layer.

Next moves are likely:

- generalize the model/tool loop out of the mortgage example
- make the agent registry more explicit instead of hardcoded wiring
- stabilize a reusable UI package instead of app-local renderers
- continue phase hardening around state versioning, HITL approvals, and observability

This makes the platform more than a demo: it is moving toward a production-style agent runtime with voice, tools, typed actions, dynamic UI, and approval workflows.
