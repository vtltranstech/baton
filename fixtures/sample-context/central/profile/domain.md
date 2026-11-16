# Sample Shop: domain context

Every agent reads this file first.

## What we are building
Prices orders and bills customers.

## Business rules (do not reinterpret)

### R1 - Overdue invoices are reminded
fields: dueDate, status
source: interview 2026-11-04 (PO), test InvoiceReminderTest.ac1_overdueInvoiceIsReminded
confirmed: true
An invoice whose due date has passed gets a reminder.

### R2 - Paid invoices are never reminded
fields: status
source: interview 2026-11-04 (PO)
confirmed: true
An invoice with status PAID is never reminded.

### R3 - Tier discounts
fields: tier
source: interview 2026-11-04 (PO)
confirmed: true
Gold customers get 10 percent off, silver 5 percent.

### R4 - Minimum invoice amount
fields: amount
source: interview 2026-11-04 (PO)
confirmed: true
An invoice is never below 1.00.

### R5 - Expired prices are ignored
fields: expiryDate, periodStart
source: interview 2026-11-04 (PO)
confirmed: true
A price that expired before the period starts is not applied.

### R6 - Rounding of yen prices
JPY prices are rounded to whole yen.

## Domain words

| word | definition | confirmed |
| --- | --- | --- |
| Invoice | A bill sent to a customer for one billing period | true |
| Customer | A party that buys and is billed | true |
| Tier | The customer's discount band: GOLD, SILVER or none | true |
| Grace Period |  | false |

## Open decisions (agents must not resolve these)
- D1: Do reminders stop after the third one? owner: PO; story: S-004
- D2: Are wholesale orders charged a surcharge?
