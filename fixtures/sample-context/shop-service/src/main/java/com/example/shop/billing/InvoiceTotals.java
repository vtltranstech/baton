package com.example.shop.billing;

import java.math.BigDecimal;

public class InvoiceTotals {

    private static final BigDecimal MINIMUM_AMOUNT = new BigDecimal("1.00");

    public BigDecimal total(Invoice invoice) {
        if (invoice == null) {
            throw new IllegalArgumentException("invoice");
        }
        BigDecimal amount = invoice.getAmount();
        if (amount.compareTo(MINIMUM_AMOUNT) < 0) {
            return MINIMUM_AMOUNT;
        }
        return amount;
    }
}
