<!-- baton:understanding area=shop-service/billing commit=fx00001 -->
# shop-service/billing

## Purpose
Billing keeps the invoices the shop issues and picks the overdue, unpaid ones that get a reminder, so fewer invoices go unpaid. [src/main/java/com/example/shop/billing/InvoiceReminder.java:8] [R1]

## What it touches
- writes collection:invoices - every issued invoice is stored here, one document per invoice [src/main/java/com/example/shop/billing/InvoiceStore.java:14]

## Rules
- bp-0001 - only invoices whose due date has passed are reminded (R1) [src/main/java/com/example/shop/billing/InvoiceReminder.java:13]
- bp-0002 - a paid invoice is never reminded (R2) [src/main/java/com/example/shop/billing/InvoiceReminder.java:14]
- bp-0003 - an invoice below the minimum amount is billed at the minimum (R4) [src/main/java/com/example/shop/billing/InvoiceTotals.java:14]

## Questions
- Q1 (open, PO): Is a reminder sent once, or again every day while the invoice stays overdue?
