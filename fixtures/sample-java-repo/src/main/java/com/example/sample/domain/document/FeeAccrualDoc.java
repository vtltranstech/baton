package com.example.sample.domain.document;

import java.math.BigDecimal;
import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.CompoundIndex;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "fee_accruals")
@CompoundIndex(name = "account_period", def = "{'accountRef': 1, 'periodKey': 1}")
public record FeeAccrualDoc(@Id String id, String accountRef, String periodKey, String feeScheduleId,
        BigDecimal amount) {
}
