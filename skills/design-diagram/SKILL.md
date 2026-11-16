---
name: design-diagram
description: How a design note gets its diagrams - the architect writes a short change spec (what is new, changed, removed, and where a new call goes) and `baton diagram story` draws the flow with impacts, sequences, low-level design, data model and use cases from the code's AST, checked against the code. Also how to read code cheaply with `baton diagram context`. Use on every design note; never hand-draw Mermaid or Structurizr DSL.
paths: ["docs/design/**", "docs/architecture/**"]
user-invocable: false
---
# Diagrams for design notes: you decide, the tool draws

You never draw a diagram by hand. Hand-written Mermaid and DSL broke (no diagram type detected, unknown identifiers, invalid dynamic views), drifted from the code, and cost thousands of tokens per story. Instead:

| Who | Does what |
| --- | --- |
| **You (architect)** | the design judgement: which methods change, what is new, where a new call goes, what is removed. Written as `docs/design/<F>/<S>-change.yaml`, usually 10-25 lines. |
| **`baton diagram story <S>`** | reads the spec and the code map (the AST of every repo + the graph), checks every name against the code, walks the code from every entry point that reaches the change, and writes the diagrams: SVG (any viewer, no plugin), Mermaid (GitHub), one-page HTML. Same input, same bytes. |

## 1. Read the code cheaply first

Before opening source files, ask for a card. It is ~20 lines for what would be several files:

```
baton diagram context OrderService          # a class: fields, methods with line ranges, calls, callers, data, tests
baton diagram context OrderService#place     # one method
baton diagram context collection:orders         # who reads / writes it, in every repo, with file:line
```
The same card is the MCP tool `graph.context` (`mcp__graph__graph_context` in a copied install, `mcp__plugin_baton_graph__graph_context` as a plugin). Open a source file only when the card does not answer the question, and then only the line range it names.

## 2. Write the change spec

`docs/design/<feature-id>/<story-id>-change.yaml` (YAML subset: no anchors, no multi-line strings):

```yaml
story: S-010
title: Apply a loyalty discount to orders
changed:                                  # existing code this story modifies
  - OrderService#place                    # a method: Class#method (simple name, or FQCN if ambiguous)
  - OrderDoc.total                        # a field
  - collection:orders                     # a resource whose shape or meaning changes
new:
  - class: com.example.orders.application.service.LoyaltyDiscountPolicy   # full name: it decides the package and file
    stereotype: service                   # controller | service | component | repository | adapter | client | publisher | listener | interface
    implements: [DiscountPolicyPort]
    uses: [OrderHistoryPort]              # injected collaborators
  - method: LoyaltyDiscountPolicy#discountFor
    signature: "discountFor(String customerRef, BigDecimal total): BigDecimal"
    calledFrom: OrderService#place        # the existing method that will call it ...
    before: PriceCalculator#calculateTotal # ... before this existing call (omit = at the end)
    calls: [OrderHistoryPort#countForCustomer]
    reads: [collection:loyalty_tiers]     # reads | writes | publishes | consumes | exposes | callsEndpoint | readsFile | writesFile
  - field: OrderDoc.discount
    type: BigDecimal
removed:                                  # breaking for every reader: the blast radius carries it
  - OrderSummary.legacyTotal
entries: []                               # optional: entry points to draw; found automatically when omitted
useCases:                                 # optional: names in the domain's words; derived from entry points when omitted
  - name: Place an order
    actor: Customer                       # a persona from profile/project.md
    entry: "endpoint:POST /api/v1/orders"
    includes: [Apply loyalty discount]
```
Rules: an existing element must exist (a typo is an error with "did you mean"); a new one must not (an existing method you modify goes under `changed`); a resource that is not in the graph yet is drawn as new; `before:` must be a call the caller already makes.

## 3. The loop

```
baton diagram story S-010 --check     # names checked against the code; prints the entry points it will draw; writes nothing
baton diagram story S-010             # writes docs/design/<F>/S-010-diagrams/
```
`--check` exit 1 lists every problem; fix the spec, never the code, and run it again. Exit 2: the story or spec file is missing. Do not hand-edit anything in `<S>-diagrams/`: it is regenerated on every run.

## 4. What you get, and where it goes in the note

`docs/design/<F>/<S>-diagrams/`:

| File | Shows | Design note section |
| --- | --- | --- |
| `flow.svg` | every component, collection, topic, file and repo on the paths the change touches, in swim lanes per repo and per data zone; NEW blue, CHANGED orange, IMPACTED red (another repo reads what changes), grey = on the path, unchanged | 3. Flow with impacts |
| `sequence-<n>.svg` | one per entry point that reaches the change (REST call, listener, job, scheduler): numbered steps, activation bars, return types, the exception path from the code, cross-repo steps; the new and changed steps are coloured and listed under the picture | 6. Sequence |
| `lld.svg` | the classes that change, with fields and methods (changed rows highlighted, new rows blue), and their collaborators one hop away | 4. Low-level design |
| `data-model.svg` | the collections on those paths with their document fields, keys and indexes; new / changed fields highlighted | 7. Data model impact |
| `use-cases.svg` | who starts each touched behaviour (personas, schedulers, publishing systems) and which other repos are affected | 5. Use cases |
| `diagrams.md` | all of the above as images + Mermaid source, plus the **touch points** table (status, element, file:lines, entry points that reach it, tests that name it) and the **blast radius** table (repo, through what, file:lines, breaking) | linked from section 3 |
| `index.html` | the same on one page for a browser | - |
| `diagrams.json` | the touch points, blast radius and entries for tools | - |

In the note, embed with plain image links - the built-in VS Code Markdown preview shows them, no extension needed:
```
## 3. Flow with impacts
![Flow with impacts](S-010-diagrams/flow.svg)
Touch points and blast radius: [S-010-diagrams/diagrams.md](S-010-diagrams/diagrams.md)
```
Under each diagram write the one sentence the reader should take from it. The impact table in section 3 is the touch-points table: link it, do not retype it. Every repo in the blast-radius table goes into section 10 Risks.

## 5. If a diagram looks wrong

It is the spec or the code, never the drawing: a missing call means the spec did not say `calledFrom`; a missing entry point means nothing in the code reaches the method (say so, or name it under `entries:`); an unexpected IMPACTED box means another repo really reads what you change: that is the finding. A walk with more than ~48 steps folds unchanged sub-flows and says so in the notes.

## 6. Light track
Write the spec too: it is a few lines and gives the touch points and blast radius for free. Section 2 of the light note links `diagrams.md`; embed only `flow.svg`.

## 7. Architecture of record
`docs/architecture/workspace.dsl` is generated by `baton c4` from the graph and is never hand-edited, so it always validates. People read `docs/architecture/diagrams/diagrams.md` (`baton diagram architecture`): system context, containers with every collection / topic / file, and the components of each repo with the calls between them. Both are regenerated after a story merges (the documentation agent), so there is no candidate workspace to write and no DSL delta to keep valid. After `/build`, `baton diagram story <S> --diff <base>` draws what was actually built into `docs/qa/<F>/<S>-as-built/` and lists what was built but not in the spec, and what is in the spec but not built.

End every Markdown artefact you write with your provenance footer, per the `workflow` skill's Provenance footer section.
