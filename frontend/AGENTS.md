<!-- BEGIN:nextjs-agent-rules -->

## This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## Project notes

- UI library: **Mantine 9** (`@mantine/core`, `dropzone`, `hooks`, `notifications`). Look up props with the `mantine` MCP server (it serves v9 docs, matching what is installed).
- Package manager: **bun**. Type-check with `bunx tsc --noEmit`, lint with `bun run lint` (ESLint 9 flat config in `eslint.config.mjs`).
- Components that pass functions as props (e.g. `<Button component={Link}>`) must live in a `'use client'` file.
- API client: `src/lib/api/*` (fetch wrapper in `client.ts`); types mirror backend Pydantic schemas in `src/types/`. Data fetching via TanStack Query hooks in `src/hooks/`; query keys in `src/lib/query-keys.ts`.
- Theme tokens (indigo primary, `accent` amber for the main CTA, Bloom colors) live in `src/theme/theme.ts`. Brand mark: `src/components/brand/LogoMark.tsx` (favicon: `src/app/icon.svg`).
