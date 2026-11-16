# Pattern ledger - which principle, and is it valid HERE

A design principle is valid only when a specific force in the story calls for it. The architect names the force; the reviewer checks the force exists. "Future flexibility" is not a force. This file is a decision table, not a textbook: the model knows what the patterns are; this says when they are legitimate on our projects. Project-specific examples live in `profile/domain.md`; the forces must come from the story.

## The ledger (mandatory in every design note, one row per new or changed class)
| Class | Principle / pattern | Force in THIS story (AC or rule id) | Simpler alternative rejected, and why | Verification (what breaks if the principle is violated) |
| --- | --- | --- | --- | --- |

A row whose Force column cites nothing concrete is INVALID and the design-review lens reports it. A row whose Simpler-alternative column is empty is INCOMPLETE. Code that applies a pattern with no ledger row is an undocumented deviation (conformance lens).

## Validity tests per pattern
| Pattern / principle | Valid when | NOT valid when (use the simpler thing) |
| --- | --- | --- |
| **Strategy** | >= 2 real variants exist TODAY and are selected at runtime | one variant; "might add more later" -> a plain method |
| **Chain of Responsibility** | an ordered walk with early exit that the domain file names as a rule; ONE implementation | any second walk of the same rule - reuse the one |
| **Template Method** | several batch steps share a skeleton with >= 2 varying hooks | one step; or variation is data, not behaviour -> parameterise |
| **Specification / predicate objects** | a business rule is combined (AND/OR) in >= 2 places | used once -> a private method with the rule's name |
| **Builder** | an immutable type with >= 5 fields or optional groups | <= 4 fields -> record constructor |
| **Repository per aggregate** | always, one per collection | a repository that joins across aggregates -> split |
| **Mapper (document <-> DTO)** | always at the API boundary | mapping inside a controller or a service method body |
| **Facade** | a UI screen or endpoint needs >= 3 services composed | wrapping one service -> call it directly |
| **Interface + single implementation** | a test needs to substitute it AND it crosses a module boundary | inside one module with one impl -> concrete class |
| **Factory** | creation depends on runtime data with >= 2 outcomes | `new` would do |
| **Event / Kafka message** | another service must react asynchronously and the story says so | in-process call would do |
| **Generic / abstract base** | >= 3 concrete uses exist now | 1-2 uses -> duplicate until the third |
| **Spring Batch** | recurring, or must resume, or needs skip/retry, or a volume per `capacity.md`, and the story states the number | a small one-off that can simply rerun -> a streaming service method |
| **WebFlux** | the service is already reactive, or streams to many slow clients | a high request rate alone -> MVC, sized from the formula in `capacity.md` |
| **Caching** | a measured hot path (AC names a latency) | speculation |
| **SRP split** | a class has >= 2 reasons to change in THIS story's diff or the next planned one | splitting a 60-line class that changes for one reason |
| **Open/Closed via extension points** | a listed open decision will plausibly change this code | no decision pending -> closed is fine |

## The three questions the architect answers in the Approach (and the lenses re-ask)
1. **Simplest design**: what is the least structure that satisfies every AC? State it in two lines.
2. **What the extra buys**: if the chosen design has more than that, which force (AC, rule, open decision) pays for each addition?
3. **Domain language**: do the type and method names use the domain's words (the list in `profile/project.md` section  Domain words) rather than Manager / Helper / Util / Processor / Handler? A generic name is the first sign the design is not shaped by the use case.

## How a principle is confirmed as applied (not just claimed)
- The ledger row names the force -> the design-review lens checks the force exists in the story.
- The conformance lens checks the code's structure matches the ledger (the class exists, the pattern is the one named, no extra pattern).
- The craft lens checks the verification column: it looks for the test or ArchUnit rule that would fail if the principle were broken; a principle with no enforceable verification is noted as "claimed, unverifiable".
- Sensors (complexity, duplication, YAGNI count) say whether the pattern earned its keep in numbers.
