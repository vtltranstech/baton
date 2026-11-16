# <app name>: agent instructions
<one line: what this UI is for and who uses it>. React 19, TypeScript strict, TanStack Query, Vite, Vitest. Started from the baton `react-ts-ui` kit. Work is driven from the central repo `<central repo>`; its `profile/` is the source of truth for domain words and the test environment.

## Build and verify
| What | Command | Report |
| --- | --- | --- |
| Install | `npm ci` | console |
| ESLint sensors | `npm run lint` (`npx eslint src --format json` for the report) | console |
| Typecheck | `npm run typecheck` | console |
| Tests | `npm test` | console |
| Build | `npm run build` | `dist/` |
| Run locally | `VITE_API_BASE_URL=<test environment url> npm run dev` | browser |

npm resolves through the org registry only (`.npmrc`, `ORG_NPM_REGISTRY`). Do not add a registry or a package from outside it. Commit `package-lock.json`.

## Layout
- `src/components`: components render only; typed props in, markup out.
- `src/hooks`: data hooks over the query client; state and effects live here.
- `src/api`: the API client module, the only place that calls `fetch`.
- `src/types`: API and prop types, mirrored from the service DTOs.
- `config/sensors/eslint-sensors.json`: the ESLint sensor rules, a copy of the baton `sensors/` file.

## Rules
- A red sensor is fixed in the code. Never edit `config/sensors/`, a threshold or an `eslint-disable` to get green; a rule believed wrong goes to `/standards record` in the central repo.
- No `fetch` in a component or hook; call the API client through a data hook.
- No `any`: declare the type in `src/types`, or use `unknown` and narrow it.
- Server state through the query client; UI state local; no global store unless two distant screens share it.
- A list and its detail pane are separate components with their own hooks; a selection changes a query key.
- No test calls a real backend; stub `fetch` at the API client.
- A new package is a design change: name it in the design note before adding it to `package.json`.
- CI runs the same pipeline for every change (`.github/workflows/ci.yml`). Do not add a skip, a condition or a separate lane.
- Do not commit to the default branch; the hooks in `.claude/settings.json` refuse it.

## Known pitfalls
(Filled by /onboard and /onboard record, with evidence.)
