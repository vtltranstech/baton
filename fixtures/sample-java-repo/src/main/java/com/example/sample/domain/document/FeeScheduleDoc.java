package com.example.sample.domain.document;

import java.math.BigDecimal;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "fee_schedules")
public record FeeScheduleDoc(@Id String id, String name, BigDecimal rate) {
}
