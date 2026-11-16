package com.example.shop.pricing;

import org.springframework.web.client.RestClient;

public class RateClient {

    private final RestClient rest;

    public RateClient(RestClient rest) {
        this.rest = rest;
    }

    public String latest() {
        return rest.get().uri("${rates.base-url}/rates").retrieve().body(String.class);
    }
}
