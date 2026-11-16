# Design (light): S-152 Show the overdue list for a billing period
Story: docs/stories/F-FIX/S-152.md   Date: 2026-11-03   Revision: 2   Track: light

## 1. Change
Add GET overdue invoices to InvoiceController; the query filters on billingPeriod first (revision 2, after QA loop 1).
Rules touched: none

## 5. Confidence
Score: 88%  Why: reuses the invoice list pattern.  Reviewer should check: the period filter.
