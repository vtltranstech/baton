# Sample context product (fixture)

`central/` is the central repo and `shop-service/` its one service repo, for `baton context` (contracts/context-map.md).

- `shop-service` has 12 planted business branch points: 3 in `billing`, 9 in `pricing`. `central/profile/branch-points.yaml` maps 5 of them to confirmed rules, so 7 are undocumented, all in `pricing`.
- `S-001` (light) names the Grace Period, a domain word with no confirmed definition: `baton context check S-001` exits 2 with that question. `S-002` is the same story as a spike: exit 0, the same gaps listed as not blocking. `S-003` (full) touches pricing and blocks on its undocumented branch points.
- `EXPECTED.json` lists the branch points the extractor must find.

Nothing here is real. `tools/baton/tests/context/` drives it.
