package com.example.sample.adapters.messaging;

import com.example.sample.application.dto.FeeSummary;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/** Its base URL is deliberately absent from application.yml: an extractor must report it as unresolved. */
@Component
public class LedgerClient {

    private final RestClient rest;

    public LedgerClient(RestClient.Builder builder, @Value("${ledger.base-url}") String baseUrl) {
        this.rest = builder.baseUrl(baseUrl).build();
    }

    public void post(FeeSummary summary) {
        rest.post().uri("/v1/postings").body(summary).retrieve().toBodilessEntity();
    }
}
