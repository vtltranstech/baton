---
name: ux-checklist
description: The UX lens checklist for a ui story's wireframe options - task fit, consistency with the screens of record and the component library, misreading risk, the five states, density and flow, accessibility - and the verdict the PO sees at gate 2a. Loaded by the UX lens of design-review-lenses.
---
Review the wireframe options of one `ui` story: $ARGUMENTS (a story id). Contract: `contracts/ui-stories.md` section 5.

Read only: `docs/design/<F>/<S>-wireframe/` (`option-*.html`, `options.md`, `screen-spec.md`, `check.json`), the story, `profile/project.md` Personas and `ui.*` keys, `docs/architecture/screens/index.md` and the screens of record of the same area, the UI module's wiki page, and `docs/qa/<F>/<S>-sensors/axe.json` when present. `baton ux check` has passed: do not re-check what it checks (sources, states present, labels in the glossary, colours).

## Checklist
1. **Task fit:** does the recommended option put the persona's first decision first? Which option serves the task best, and why, in one line each.
2. **Consistency:** region by region against the screens of record and the library: the same pattern and component, or a justified departure. Name the reference screen id. A `New:` component that duplicates a library or app component is a finding.
3. **Misreading risk (HIGH):** any number, date, status or currency that could be read as something else: money without its currency, a period shown as a date, a total over partial data, a status shown by colour alone, a count without its unit.
4. **States:** each of the five suits this persona; the empty state says what to do next; the error state says how to fix, never a code; partial data never shows a total as if complete.
5. **Density and flow:** decisions per screen, scrolling needed for the primary decision, dead ends, an action far from what it acts on.
6. **Accessibility:** interpret `axe.json`; then what axe cannot see: reading order, label clarity, focus order, keyboard reach of row actions, error messages that say how to fix.
7. **Verdict:** `approve as planned`, `approve with changes 1-n` or `rework`, with at most three concrete changes, each tied to a persona, a rule id or a reference screen. The verdict is a recommendation; the PO decides.

## Output - `docs/design/<F>/<S>-reviews/ux.md`
```
# UX lens: <S>

Verdict: <approve as planned | approve with changes 1-n | rework>
Recommended option: <n> (<agree with options.md | prefer n: why>)
1. Task fit: ...
2. Consistency: ...
3. Misreading risk: ...
4. States: ...
5. Density and flow: ...
6. Accessibility: ...

| Finding | Severity | PO |
| --- | --- | --- |
| <the change, tied to a persona, rule id or screen id> | HIGH / MEDIUM / LOW | agree / disagree (the PO fills this at gate 2a) |
```
ASCII only. Return the verdict, the HIGH count and the file path; nothing else.
