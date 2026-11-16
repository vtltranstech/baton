# Kit: react-ts-ui
A React 19 + TypeScript (strict) UI on Vite, with the baton ESLint sensors already in the build. Example: an `ItemPanel` that reads one item from `/api/v1/items/{itemKey}` and renders it in an `ItemCard`; to replace with the real screens.

## What it gives
- Layout the extractors read: `src/components`, `src/hooks` (TanStack Query), `src/api` (the client module), `src/types`.
- Sensors: `eslint.config.js` (flat config) with the rules of `config/sensors/eslint-sensors.json`, `tsconfig.json` with `strict`, `npm test` (Vitest, jsdom).
- Tests: a component test, an API client test with a stubbed `fetch`.
- Claude Code: `.claude/settings.json` (baton hooks, as `templates/settings.json`), `CLAUDE.md` importing `AGENTS.md`.
- CI: `.github/workflows/ci.yml`, the same pipeline for every change.
- `RUNBOOK.md` stub, `.gitignore`, `.npmrc` (org registry via `ORG_NPM_REGISTRY`).

## Start a repo from it
1. Copy this folder to the new repo and `git init`.
2. Set `name` in `package.json` and every `<angle bracket>` placeholder.
3. Replace `item` with the real resource; keep the folders.
4. Copy `.claude/hooks/` from the central repo; until it is there, every hook refuses.
5. Set `ORG_NPM_REGISTRY`, run `npm install` once, commit `package-lock.json` (CI runs `npm ci`), push, and turn on branch protection for the default branch.
6. In the central repo, add the row to `profile/project.md` and run `/onboard`.

## What /onboard still asks
- The repo table row in the central repo's `profile/project.md`: path, purpose, build command.
- The domain words the screens use, for the naming checks.
- The test environment: its name and the backend URL the UI points at there.
- Anything the extractors report as `unknown`.

Not verified here: the kit was not installed, linted or built, because nothing may be downloaded outside the org registry. The ESLint config and versions match `fixtures/sample-react-repo`.
