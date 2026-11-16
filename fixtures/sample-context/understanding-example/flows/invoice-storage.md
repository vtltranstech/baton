# Flow: an issued invoice is stored and reported

## Trigger
An invoice is issued for a customer.

## Steps
1. shop-service/billing writes collection:invoices - the invoice is saved with its due date, status and amount [src/main/java/com/example/shop/billing/InvoiceStore.java:14]
2. external:Reporting reads collection:invoices - the finance reports read the stored invoices, as the Tech Lead answered in the landscape
