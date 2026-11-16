# Flow: an order is priced

## Trigger
A customer places an order and the shop needs its price.

## Steps
1. external:Catalogue writes collection:prices - the catalogue team maintains the price list, as the landscape records
2. shop-service/pricing reads collection:prices - the active price in the order's currency is loaded [src/main/java/com/example/shop/pricing/PriceRepository.java:9]
3. shop-service/pricing calls endpoint:GET ${rates.base-url}/rates - the latest exchange rates are fetched [src/main/java/com/example/shop/pricing/RateClient.java:14]
4. external:Rates exposes endpoint:GET ${rates.base-url}/rates - the rates system answers with today's rates
