package com.example.shop.pricing;

import static java.math.RoundingMode.HALF_EVEN;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.Optional;

public class PriceResolver {

    private static final BigDecimal GOLD_DISCOUNT = new BigDecimal("0.10");
    private static final BigDecimal SILVER_DISCOUNT = new BigDecimal("0.05");

    public BigDecimal resolve(Price price, Customer customer, LocalDate periodStart) {
        if (price == null) {
            throw new IllegalArgumentException("price");
        }
        if (price.getExpiryDate().isBefore(periodStart)) {
            return BigDecimal.ZERO;
        }
        BigDecimal base = price.getAmount();
        switch (customer.getTier()) {
            case GOLD -> base = base.subtract(base.multiply(GOLD_DISCOUNT));
            case SILVER -> base = base.subtract(base.multiply(SILVER_DISCOUNT));
            default -> { }
        }
        return customer.getCurrencyCode().equals("JPY") ? base.setScale(0, HALF_EVEN) : base.setScale(2, HALF_EVEN);
    }

    public Optional<Price> promotional(Optional<Price> price) {
        return price.filter(p -> p.getPromoFlag());
    }
}
