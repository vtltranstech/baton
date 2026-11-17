# sample-ui: fixture for UI stories (contracts/ui-stories.md)

Copied next to a copy of `sample-central-repo` by `tools/baton/tests/test_ux.py`:
- `library/` stands for the organisation's component library (`ui.library.path`): components in source (`src/`), typings (`types/index.d.ts`) and one Markdown page (`docs/StatePanel.md`).
- `invoice-ui/` is the UI repo before the story: one route, `/invoices`.
- `built/` is what the developer adds for S-120: the `/invoices/:invoiceId` screen, built from the library.
- `central/` is laid over the central repo: `profile/dependencies.yaml` with the invoice endpoints, feature F-300, stories S-120 (full track, a new screen, three options) and S-121 (light track, a delta adding `dueDate`).
