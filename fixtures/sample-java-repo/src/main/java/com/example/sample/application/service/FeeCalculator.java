package com.example.sample.application.service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import org.springframework.stereotype.Component;

/** The one implementation of the named rule "fee calculation". */
@Component
public class FeeCalculator {

    private static final int SCALE = 2;
    private static final BigDecimal MINIMUM_FEE = new BigDecimal("1.00");

    public BigDecimal calculateFee(BigDecimal balance, BigDecimal rate) {
        BigDecimal fee = balance.multiply(rate).setScale(SCALE, RoundingMode.HALF_EVEN);
        if (fee.compareTo(MINIMUM_FEE) < 0) {
            return MINIMUM_FEE;
        }
        return fee;
    }
}
