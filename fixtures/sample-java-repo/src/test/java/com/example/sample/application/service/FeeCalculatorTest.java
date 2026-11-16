package com.example.sample.application.service;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class FeeCalculatorTest {

    private final FeeCalculator calculator = new FeeCalculator();

    @Test
    void feeIsBalanceTimesRateRoundedHalfEven() {
        assertEquals(new BigDecimal("12.34"), calculator.calculateFee(new BigDecimal("1234.40"), new BigDecimal("0.01")));
    }

    @Test
    void feeBelowTheMinimumIsRaisedToTheMinimum() {
        assertEquals(new BigDecimal("1.00"), calculator.calculateFee(new BigDecimal("10.00"), new BigDecimal("0.01")));
    }
}
