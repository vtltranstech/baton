package com.example.sample.adapters.messaging;

import com.example.sample.application.port.RatePort;
import java.math.BigDecimal;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class RateClient implements RatePort {

    private final RestClient rest;

    public RateClient(RestClient.Builder builder, @Value("${rates.base-url}") String baseUrl) {
        this.rest = builder.baseUrl(baseUrl).build();
    }

    @Override
    public BigDecimal currentRate(String currency) {
        return rest.get().uri("/v1/rates/{currency}", currency).retrieve().body(BigDecimal.class);
    }
}
