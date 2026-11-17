# Screen: invoice-summary
persona: Billing Clerk
task: decide whether an invoice can be sent
area: invoice-ui
route: /invoices/{invoiceId}
entry-points: invoice list row
screen-of-record: docs/architecture/screens/invoice-summary

## Regions
| region | purpose | fields / actions | component |
| --- | --- | --- | --- |
| header | which invoice | customerName, billingPeriod, dueDate | PageHeader |
| totals | the decision | total, status | InvoiceTotals |
| lines | what makes the total | description, amount | DataTable |
| actions | what the clerk can do | send | ActionBar |

## Fields
| field | label | source | format | rule |
| --- | --- | --- | --- | --- |
| customerName | Customer | GET /invoices/{id} -> customerName | text | - |
| billingPeriod | Billing period | route param -> billingPeriod | YYYY-MM | - |
| dueDate | Due date | GET /invoices/{id} -> dueDate | YYYY-MM-DD | - |
| total | Total | GET /invoices/{id} -> total | money, 2 dp, with currency | R2 |
| status | Status | GET /invoices/{id} -> status | word, never a colour alone | - |
| description | Description | GET /invoices/{id} -> lines[].description | text | - |
| amount | Amount | GET /invoices/{id} -> lines[].amount | money, 2 dp, with currency | R2 |

## Actions
| action | label | target | permission |
| --- | --- | --- | --- |
| send | Send | POST /invoices/{id}/send | invoice:send |

## States
| state | when | shows |
| --- | --- | --- |
| loading | request in flight | skeleton rows, header stays |
| empty | the invoice has no lines | "No lines for this period" and how to add one |
| error | 4xx or 5xx | message and retry; never a stack trace |
| partial | a line is unresolved | the line flagged, total hidden |
| no-permission | 403 | explanation, no data |

## Validation and rules on screen
- the total shows only when every line is resolved (R2)

## Accessibility notes
- the lines table has a caption and header scope; focus order is reading order
