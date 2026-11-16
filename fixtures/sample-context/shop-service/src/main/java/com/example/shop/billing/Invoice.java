package com.example.shop.billing;

import java.math.BigDecimal;
import java.time.LocalDate;

public record Invoice(String id, LocalDate dueDate, String status, BigDecimal amount) {

    public LocalDate getDueDate() {
        return dueDate;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getAmount() {
        return amount;
    }
}
