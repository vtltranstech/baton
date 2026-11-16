package com.example.shop.billing;

import java.time.LocalDate;
import java.util.List;

public class InvoiceReminder {

    public List<Invoice> toRemind(List<Invoice> invoices, LocalDate today) {
        if (invoices.isEmpty()) {
            return List.of();
        }
        return invoices.stream()
                .filter(i -> i.getDueDate().isBefore(today))
                .filter(i -> !"PAID".equals(i.getStatus()))
                .toList();
    }
}
