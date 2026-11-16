package com.example.shop.pricing;

import java.math.BigDecimal;

public class SurchargeCalculator {

    private static final BigDecimal RUSH_FEE = new BigDecimal("5.00");

    public BigDecimal surcharge(Order order) {
        BigDecimal extra = BigDecimal.ZERO;
        if (order.getRegionCode() != null && order.getRegionCode().startsWith("EU")) {
            extra = extra.add(BigDecimal.ONE);
        } else if (order.getOrderType() == OrderType.WHOLESALE) {
            extra = extra.subtract(BigDecimal.ONE);
        }
        return order.isRushFlag() ? extra.add(RUSH_FEE) : extra;
    }
}
