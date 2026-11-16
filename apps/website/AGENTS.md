# Relay website (marketing page + Experience Center)

- Next.js 16 — APIs differ from older versions; read `node_modules/next/dist/docs/` before changing routing, params or caching.
- The example gallery is driven by `lib/examples.ts` only. To add an example: add an entry there (and its `NEXT_PUBLIC_EXAMPLE_*_URL`); the example app itself must support sandbox mode (`examples/shared/sandbox`, see `docs/experience-center.md`).
- Code samples on the page must match the real SDK/CLI API (`packages/web-sdk/docs/`).
