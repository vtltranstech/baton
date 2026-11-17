# UI stories - wireframe, component library, UX lens, gate 2a, screens of record

Extends the architect, `design-review-lenses`, `baton build`, the developer, the documentation agent and the UI starter kit. No new agent: the architect gains a UI mode; UX review is a lens; approval is human. Applies to any story with the label `ui` (set by `/stories` when a feature touches a screen, or by a human).

## 1. Flow for a `ui` story (inside `baton build`)

| Step | Who | Produces | Gate |
| --- | --- | --- | --- |
| wireframe | architect (UI mode) | `docs/design/<F>/<S>-wireframe/option-{1..3}.html`, `screen-spec.md`, `options.md` (rationale per option, one marked recommended) | - |
| ux-check | `baton ux check S`, run by `baton build` | `<S>-wireframe/check.json`, `screen-spec.json` | a failure sends the wireframe back to the architect |
| ux-lens | UX lens (`design-review-lenses`, `ux-checklist`) | `docs/design/<F>/<S>-reviews/ux.md`; `axe.json` when the kit's runner is available | - |
| **gate 2a** | the PO, with the designer when `ui.designer` names one | `baton ux show S --open` puts the options side by side; the choice goes in the story under `## Wireframe approval`; `approved.html` | the question: Option 1 / 2 / 3 / Changes / Block (at most 2 rounds of changes) |
| architect | architect (normal) | the design note, citing `approved.html` and `screen-spec.md` in sections 3, 3a (C4 delta for the UI container) and 8 | - |
| gate 2 | the Senior Engineer reads, the Tech Lead decides | as today | as today |
| build, sensors, QA, security | as today, plus `baton ux verify S` (section 7) and the axe sensor on the built screen | `docs/qa/<F>/<S>-ui-verify.json` | - |
| promote | documentation | `baton ux promote S`: `docs/architecture/screens/<screen-id>/` (section 6) | - |

The State stays `Ready` (or `Design Changes Requested`) through the wireframe steps; the build ledger (`<S>-build.json`) records `wireframe`, `ux-check`, `ux-lens` and `gate2a`. No new State.

**Light track collapse.** A `ui` story on the light track changes an existing screen of record: the architect writes one wireframe, `option-1.html`, as a delta on the screen of record (changed regions carry `data-changed`), and the spec delta. No UX lens. Gate 2a and gate 2 are one question to the PO and the Tech Lead together: `approve wireframe + design / changes / block`; there is no auto-pass. A new screen is always full track: `baton ux check` refuses `screen-of-record: new` on the light track.

## 2. The architect's UI mode (`agents/architect.md`)
Triggered by the `ui` label, before any technical design. Inputs: the story and its manifest, `profile/project.md` Personas and `ui.*` keys, `profile/ui-inventory.yaml` (section 4), the screens of record in the same area (`docs/architecture/screens/index.md`), the UI module's wiki page, `profile/dependencies.yaml`, the data profile of every collection the screen reads, the glossary (`profile/domain.md` Domain words).

- **Up to three options**, lo-fi, from `templates/ui/wireframe.html` and `wireframe.css`. Options differ in information hierarchy or interaction model, never in colour. Each has a rationale in `options.md`: the persona's first decision on this screen, what is above the fold and why, which screen of record it follows (screen id) or why it departs. One option is marked `(recommended)`.
- **`screen-spec.md`** (section 3): the one artefact the developer builds from and the checks read.
- **Components first:** every region names the component it is built from: a component of the organisation's library (`ui.library`), an existing app component, or `New: <Name> (<library>: A, B)` composed from library components. A region that exists on a screen of record is referenced, not redrawn.
- **Never:** colours, fonts, logos or images (`baton ux check` fails an option with `<img>`, a colour, a `font-family` or a script); a label that is not a glossary word or a field name; a field or action on the wireframe that the spec lacks; technical words on screen (`id`, `null`, `undefined`, collection names).

## 3. `screen-spec.md` (JSON twin `screen-spec.json`, schema `schemas/screen-spec.json`)

```
# Screen: invoice-summary
persona: Billing Clerk
task: decide whether an invoice can be sent before month-end
area: invoice-ui
route: /invoices/{invoiceId}
entry-points: invoice search results row
screen-of-record: new            (or: docs/architecture/screens/invoice-summary)

## Regions
| region | purpose | fields / actions | component |
| --- | --- | --- | --- |
| header | which invoice | customerName, billingPeriod | PageHeader |
| totals | the decision | total, status | New: InvoiceTotals (library: Card, Stat) |
| actions | what the clerk can do | send | ActionBar |

## Fields
| field | label | source | format | rule |
| --- | --- | --- | --- | --- |
| total | Total | GET /invoices/{id} -> total | money, 2 dp, with currency | R2 |
| billingPeriod | Billing period | route param -> billingPeriod | YYYY-MM | - |

## Actions
| action | label | target | permission |
| --- | --- | --- | --- |
| send | Send | POST /invoices/{id}/send | invoice:send |

## States
| state | when | shows |
| --- | --- | --- |
| loading | request in flight | skeleton rows, header stays |
| empty | no lines | "No lines for <period>" and a link to add one |
| error | 4xx or 5xx | message and retry; never a stack trace |
| partial | a line is unresolved | the line flagged, total hidden |
| no-permission | 403 | explanation, no data |

## Validation and rules on screen
- the total shows only when every line is resolved (R2)

## Accessibility notes
- the table has a caption and header scope; focus order is reading order
```

- **Sources:** `METHOD /path -> field` (an endpoint in `profile/dependencies.yaml`, path parameters matched by position), `route param -> x`, `query param -> x`, `derived: <how>`, `static`, or `new: METHOD /path -> field` (an endpoint the design must declare in its C4 delta; listed by the check).
- **Targets:** an endpoint as above, `route: /path` (a route in the inventory or on a screen of record), or `new: ...`.
- **`baton ux check S`** fails, exit 1, one line per problem, when: a field's source or an action's target does not resolve (also written as a question for the PO or Tech Lead in `check.json`; gate 2a cannot pass with one); a region's component is not in the inventory and not declared new, or a `New:` component names no library component while `ui.library` is set; one of the five states is missing; a rule id is not a `### R<n>` in `profile/domain.md`; a field label uses a word that is neither in the glossary nor in a field name; a wireframe option has a field, action or region the spec lacks, or a colour, font, image or script; the light track has `screen-of-record: new`; the full track has no `options.md` or no option marked recommended. Exit 2 when the spec or the wireframe folder is missing.

## 4. Component inventory and the organisation's library

| Key in `profile/project.md` | Means |
| --- | --- |
| `ui.library` | the library's name, e.g. the organisation's framework; `none` for a product without one |
| `ui.library.path` | the folder(s) holding it, relative to the central repo, separated by commas: its source (`.ts`, `.tsx`, `.js`, `.jsx`), its typings (`.d.ts`), or one Markdown page per component (`# Name`, a props table) |
| `ui.library.import` | the package(s) screens import it from, e.g. `@org/ui` |
| `ui.library.forbid` | packages screens must not import directly (the library wraps them), e.g. `@mui/*, antd` |
| `ui.designer` | who joins gate 2a, or `none` |
| `ui.budgets` | Core Web Vitals budget for the built screen, e.g. `LCP 2500, CLS 0.1, INP 200` |

`baton extract --ui` (same as `baton ux inventory`) writes `profile/ui-inventory.yaml`: the library's components with their props and files; per UI repo (a repo with `package.json`), its routes with the component each renders, its exported components with props, the UI packages it depends on, and what it imports from each. Read with regular expressions, no Node and no network. Run it after `/onboard`, and again when the library folder changes.

## 5. The UX lens (`design-review-lenses`, role skill `ux-checklist`)
Runs after `baton ux check` passes, full track only, fresh context, the `design-lenses` model of `baton models S`. Reads: the options, `options.md`, the spec, the personas, the area's screens of record, the UI wiki page, `axe.json` when present. Writes `docs/design/<F>/<S>-reviews/ux.md`:

1. **Task fit:** does the recommended option put the persona's first decision first; which option serves the task best and why.
2. **Consistency:** region by region against the screens of record and the library: same pattern and component, or a justified departure; name the reference screen.
3. **Misreading risk** (HIGH): a number, date, status or currency that could be read as something else: money without currency, a period shown as a date, totals over partial data, a status colour without a word.
4. **States:** each of the five is sensible for this persona; the empty state says what to do next.
5. **Density and flow:** decisions per screen, scrolling needed for the primary decision, dead ends.
6. **Accessibility:** reads `axe.json`, and adds what axe cannot see: reading order, label clarity, error messages that say how to fix.
7. **Verdict:** `approve as planned`, `approve with changes 1-n` or `rework`, with at most three concrete changes, each tied to a persona, a rule id or a reference screen. The verdict is a recommendation; the PO decides.

Findings carry a severity; a HIGH counts toward the design confidence like any blocking lens finding. Each finding has a `PO: agree | disagree` cell the PO fills at gate 2a; `/retro` computes UX-lens precision from it.

## 6. Screens of record - `docs/architecture/screens/<screen-id>/`
The UI counterpart of `workspace.dsl`. Each folder: `approved.html` (the wireframe as last approved), `screen-spec.md` (stamped `baton.story`, `baton.feature`, `baton.since`), `history.md` (one line per story: date, story, regions and fields added, removed or changed), and `built.png` when the kit's runner took one. `docs/architecture/screens/index.md` lists every screen: route, persona, area, last story.

- **Promotion:** `baton ux promote S`, run by the documentation agent after gate 3, never at approval. Exit 2 without an approved wireframe and spec.
- **Compare:** `baton ux diff <screen-id> <refA> <refB> [--out F.html]` renders the spec's regions at two git refs (or two files) side by side, changed regions outlined; from the region list, not from images.
- The architect's components-first rule and the UX lens's consistency check both read here, so the first approved screens become the product's pattern library.

## 7. Conformance of the built screen - `baton ux verify S`
Static and deterministic: it reads the screen's source in the UI repo's working tree (the route's component from the inventory, or the spec's `files:` header, and the local components they import), and checks against the spec:

| Mismatch | Severity |
| --- | --- |
| a spec field without `data-field="<field>"`, an action without `data-action`, a state without `data-state` | HIGH |
| a direct import from a `ui.library.forbid` package | HIGH |
| a field whose label text is not in the source (label drift) | MEDIUM |
| a `data-field` the spec lacks | MEDIUM |
| a region's library component not imported by the screen | MEDIUM |

Output `docs/qa/<F>/<S>-ui-verify.json` `{story, screen, files, mismatches[{severity, kind, what}], ok}`; exit 1 on a HIGH. The conformance lens reads this file and the diff; it does not re-derive what the check proved. Rendering each state in a browser is the kit's Playwright runner (section 8), where the org's npm registry provides it.

## 8. Sensors for UI (the `react-ts-ui` kit)
- **axe** (WCAG 2.2 AA) through Playwright on every wireframe option and on the built screen: `axe.json` in `docs/qa/<F>/<S>-sensors/`; a serious or critical violation is red, like a red ArchUnit.
- **Core Web Vitals** against `ui.budgets`: `web-vitals.json`; over budget is a finding, not red, until the first calibration.
- ESLint with `jsx-a11y`, and `no-restricted-imports` for the `ui.library.forbid` packages.
- Raw Playwright traces go to the CI store, never to Git.

## 9. Lo-fi stylesheet and template - `templates/ui/wireframe.css`, `wireframe.html`
Grey boxes, 1px borders, the system font only, three text sizes, placeholders for tables and charts, each region outlined with its name as a caption. Attributes the checks rely on: `data-region`, `data-field`, `data-action`, `data-state`, `data-component`, `data-changed` (light delta). The stylesheet has no colour variables on purpose.

## 10. Confidence and metrics
- **Confidence:** a HIGH in `ui-verify.json` makes the conformance signal 0, a MEDIUM halves it; a serious or critical axe violation makes the sensors signal red.
- **Metrics:** rows gain `wireframe_rounds` and `ux_findings_high`; `/retro` reports the gate 2a wait and the UX-lens precision.

## 11. Limits
- Lo-fi wireframes decide layout, information and states; they do not decide visual design. The library's own tokens and the kit's lint check the look, not the lens.
- The inventory and `ux verify` read source with regular expressions: a component built by a factory, or a field rendered without its `data-field`, is not seen.
- Nothing in the core renders a page: axe, Web Vitals and screenshots need Playwright from the org's npm registry.

## 12. Differences from the source guide
- **Names:** `baton`, not `pod`; `baton extract --ui` and `baton ux inventory` are the same.
- **Components in the spec:** each region's component is a column of the spec's Regions table, the one file the developer reads, not a table in `options.md`.
- **The organisation's library** (section 4) is an addition: regions are built from it, `New:` components say which of its parts they compose, and direct imports of what it wraps are refused.
- **`ux verify` is static** in the core; rendering stays in the kit.
- **`ux show`** is an addition: the options side by side for the PO, opened in a browser.
- **`ux promote`** is an addition: the documentation agent runs it, so promotion is deterministic.
