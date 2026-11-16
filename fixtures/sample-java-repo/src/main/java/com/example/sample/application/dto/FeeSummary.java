package com.example.sample.application.dto;

import java.math.BigDecimal;

public record FeeSummary(String accountRef, String periodKey, BigDecimal total) {
}
