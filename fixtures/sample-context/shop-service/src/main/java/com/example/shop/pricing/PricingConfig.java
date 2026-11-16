package com.example.shop.pricing;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Configuration;

@Configuration
@ConditionalOnProperty(name = "pricing.tier-discounts.enabled", havingValue = "true")
public class PricingConfig {
}
