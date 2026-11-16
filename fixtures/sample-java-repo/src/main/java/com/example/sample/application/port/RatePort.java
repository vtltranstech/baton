package com.example.sample.application.port;

import java.math.BigDecimal;

public interface RatePort {

    BigDecimal currentRate(String currency);
}
