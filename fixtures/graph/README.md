# fixtures/graph: 3-repo blast-radius fixture

A central repo layout (`profile/`) consumed by `tools/baton/tests/W5`. `dependencies.yaml` follows
`schemas/dependencies.json`; it is hand-written against the contract, not extractor output.

| Shared thing | Writer | Readers |
| --- | --- | --- |
| `collection:accounts` | ledger-loader | account-service (line 14), statement-batch (lines 41 and 58) |
| `topic:account.events` | ledger-loader | account-service (22), statement-batch (18) |
| `file:outbound/accounts-*.csv` | ledger-loader | statement-batch (25) |
| `endpoint:GET /api/v1/accounts/{id}` | account-service | statement-batch (52) |
| `topic:statement.ready` | statement-batch | ledger-loader (12), depth-2 path |

Planted unknown edge: `queue:SETTLEMENT.IN` is published by ledger-loader and has no consumer.
`inputs/` holds the diffs and design file list; `expected/` the exact `impact.json` results.
