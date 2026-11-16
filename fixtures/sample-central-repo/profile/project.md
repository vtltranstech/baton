# Project profile: Sample Product

| Key | Value |
| --- | --- |
| project.name | Sample Product |
| project.one-liner | Records invoices and their payments |
| test.env | TEST |
| test.env.uri.var | TEST_URI |
| forbidden.envs | anything not TEST |
| period.key | billingPeriod |
| jira.labels.extra | outbound-file |
| core.version | 0.2.0 (baton) |
| hotfix.policy | gate 2 skipped; PR labelled hotfix; same-day human merge |
| track.auto-pass.confidence | 80 |
| estimate.lines.S | 300 |
| estimate.lines.M | 800 |

## Repos (siblings of this folder)
| Path | What it is | Build |
| --- | --- | --- |
| `../invoice-service` | Invoice APIs | mvn -q clean verify |

## Domain words
Invoice, Payment, Customer, BillingPeriod

## Personas
Billing Clerk, Tech Lead
