# Relay website (marketing page + Experience Center)

- Next.js 16 — APIs differ from older versions; read `node_modules/next/dist/docs/` before changing routing, params or caching.
- The example gallery is driven by `lib/examples.ts` only. To add an example: add an entry there (and its `NEXT_PUBLIC_EXAMPLE_*_URL`) and a 1200×750 WebP screenshot of its home page at `public/examples/<slug>.webp` (cards show it); the example app itself must support sandbox mode (`examples/shared/sandbox`, see `docs/experience-center.md`).
- Code samples on the page must match the real SDK/CLI API (`packages/web-sdk/docs/`).

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
