package com.example.sample.adapters.messaging;

import com.example.sample.application.dto.FeeSummary;
import com.example.sample.application.port.PostingPort;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class AccrualPublisher implements PostingPort {

    private final KafkaTemplate<String, FeeSummary> kafka;

    public AccrualPublisher(KafkaTemplate<String, FeeSummary> kafka) {
        this.kafka = kafka;
    }

    @Override
    public void post(FeeSummary summary) {
        kafka.send("fee.accrual.posted", summary.accountRef(), summary);
    }
}
