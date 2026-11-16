package com.example.sample.adapters.messaging;

import com.example.sample.application.service.FeeService;
import java.math.BigDecimal;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class FeeEventListener {

    private final FeeService fees;

    public FeeEventListener(FeeService fees) {
        this.fees = fees;
    }

    @KafkaListener(topics = "${fee.events-topic}", groupId = "sample")
    public void onFeeEvent(FeeEvent event) {
        fees.accrue(event.accountRef(), event.periodKey(), event.scheduleId(), event.balance());
    }

    /** Inbound Kafka payload. */
    public record FeeEvent(String accountRef, String periodKey, String scheduleId, BigDecimal balance) {
    }
}
