package com.example.sample.adapters.messaging;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
public class AdjustmentListener {

    private final JmsTemplate jms;

    public AdjustmentListener(JmsTemplate jms) {
        this.jms = jms;
    }

    @JmsListener(destination = "FEE.ADJUSTMENT.IN")
    public void onAdjustment(String adjustmentRef) {
        jms.convertAndSend("FEE.ADJUSTMENT.ACK", adjustmentRef);
    }
}
