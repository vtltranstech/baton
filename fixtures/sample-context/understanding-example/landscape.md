# Landscape

## Systems
| system | direction | how | resource | evidence |
| --- | --- | --- | --- | --- |
| Reporting | downstream | shared collection | collection:invoices | Q1 |
| Catalogue | upstream | shared collection | collection:prices | Q2 |
| Rates | downstream | http | endpoint:GET ${rates.base-url}/rates | [shop-service/src/main/java/com/example/shop/pricing/RateClient.java:14] |

## Questions
- Q1 (blocking, TL): Who reads collection:invoices besides billing?
  answer: The finance reporting job reads it nightly (Tech Lead, 2026-11-13)
- Q2 (blocking, TL): Which system writes collection:prices?
  answer: The catalogue service owned by the merchandising team (Tech Lead, 2026-11-13)
