package com.example.sample.adapters.controller;

import com.example.sample.application.dto.FeeSummary;
import com.example.sample.application.service.FeeService;
import java.math.BigDecimal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/fees")
public class FeeController {

    private final FeeService fees;

    public FeeController(FeeService fees) {
        this.fees = fees;
    }

    @GetMapping("/{accountRef}")
    public FeeSummary summary(@PathVariable String accountRef, @RequestParam String periodKey) {
        return fees.summarise(accountRef, periodKey);
    }

    @PostMapping("/{accountRef}/accruals")
    public FeeSummary accrue(@PathVariable String accountRef, @RequestParam String periodKey,
            @RequestParam String scheduleId, @RequestParam BigDecimal balance) {
        return fees.accrue(accountRef, periodKey, scheduleId, balance);
    }
}
