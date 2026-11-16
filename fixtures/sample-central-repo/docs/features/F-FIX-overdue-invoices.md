# F-FIX Clerks see which invoices are overdue

Owner: Pat Example
Date: 2026-11-02

## Problem
Clerks find overdue invoices by sorting a spreadsheet each morning. Late reminders cost goodwill.

## Outcome
Every morning each clerk sees the invoices that became overdue, and the customer gets a notice.

## Who
Billing Clerk.

## What the user can do
1. See the list of overdue invoices for a billing period.
2. Know that each overdue customer was sent one notice.

## Business rules
- An invoice is overdue 30 days after its due date when it is unpaid.

## Scope for this release
- Overdue list for one billing period.
- One notice per overdue invoice.

## Out of scope
- Reminders after the first notice.
