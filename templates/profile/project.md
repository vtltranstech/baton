# Project profile: <project name>   (only what the build files cannot tell us)

| Key | Value |
| --- | --- |
| project.name | <project name> |
| project.one-liner | <one line> |
| test.env | <test environment name> |
| test.env.uri.var | <NAME_OF_ENV_VAR_HOLDING_THE_TEST_URI> |
| forbidden.envs | anything not <test environment name> |
| period.key | <period or partition key, or none> |
| jira.project.key | (fill) |
| jira.site | (fill) |
| jira.labels.extra | <labels that force a design review, or none> |
| core.version | 0.2.0 (baton) |
| hotfix.policy | gate 2 skipped; PR labelled hotfix; same-day human merge |
| track.auto-pass.confidence | 80 |
| estimate.lines.S | 300 |
| estimate.lines.M | 800 |
| ui.library | <the organisation's UI component library, or none> |
| ui.library.path | <its folder(s), relative to this repo, e.g. ../ui-library/src; source, typings or one .md per component> |
| ui.library.import | <the package screens import it from, e.g. @org/ui> |
| ui.library.forbid | <packages screens must not import directly, e.g. @mui/*, or none> |
| ui.designer | <who joins gate 2a, or none> |
| ui.budgets | LCP 2500, CLS 0.1, INP 200 |

## Repos (siblings of this folder)
| Path | What it is | Build |
| --- | --- | --- |
| `../<repo>` | <purpose> | <build command> |

## Domain words (used by the craft, domain and design lenses for the naming check)
<ten or so terms; their definitions go in the Domain words table of profile/domain.md>

## Personas (elicitation and story roles)
<roles>

## Project-specific sensor additions (beyond the core Java/React set)
- (none yet; added only through /standards record)
