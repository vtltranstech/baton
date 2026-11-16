<!-- baton:understanding area=shop-service/pricing commit=fx00001 -->
# shop-service/pricing

## Purpose
Pricing works out what a customer pays for an order: the current price, the customer's tier discount, surcharges and rounding by currency. [src/main/java/com/example/shop/pricing/PriceResolver.java:14] [R3]

## What it touches
- reads collection:prices - the active prices per currency that every order is priced from [src/main/java/com/example/shop/pricing/PriceRepository.java:9]
- calls endpoint:GET ${rates.base-url}/rates - fetches the latest exchange rates from the rates system [src/main/java/com/example/shop/pricing/RateClient.java:14]

## Rules
- bp-0004 - a price that expired before the billing period starts is ignored (R5) [src/main/java/com/example/shop/pricing/PriceResolver.java:18]
- bp-0005 - gold and silver customers get their tier discount (R3) [src/main/java/com/example/shop/pricing/PriceResolver.java:22]
- bp-0006 - only ACTIVE prices in the order's currency are used; which rule says so? (Q1) [src/main/java/com/example/shop/pricing/PriceRepository.java:9]
- bp-0007 - yen prices are rounded to whole units, others to cents (Q2) [src/main/java/com/example/shop/pricing/PriceResolver.java:27]
- bp-0008 - only prices flagged as promotional count as promotions (Q3) [src/main/java/com/example/shop/pricing/PriceResolver.java:31]
- bp-0009 - tier discounts can be switched off by configuration (Q4) [src/main/java/com/example/shop/pricing/PricingConfig.java:7]
- bp-0010 - orders from EU regions pay one unit more (Q5) [src/main/java/com/example/shop/pricing/SurchargeCalculator.java:11]
- bp-0011 - wholesale orders pay one unit less (Q5) [src/main/java/com/example/shop/pricing/SurchargeCalculator.java:13]
- bp-0012 - a rush order pays the rush fee (Q6) [src/main/java/com/example/shop/pricing/SurchargeCalculator.java:16]

## Contradictions
- None found: no architecture diagram has been generated for this product yet.

## Questions
- Q1 (blocking, PO): Which rule says only ACTIVE prices are used, and what makes a price active?
- Q2 (blocking, PO): Is rounding yen to whole units a business rule (R6 is not confirmed) or a technical choice?
- Q3 (blocking, PO): What makes a price promotional, and who sets the flag?
- Q4 (blocking, PO): When are tier discounts switched off, and who decides?
- Q5 (blocking, PO): Why do EU orders pay more and wholesale orders less, and is it always exactly one unit?
- Q6 (blocking, PO): What is the rush fee for, and is 5.00 fixed?
