package com.example.sample.application.service;

import com.example.sample.application.dto.FeeSummary;
import com.example.sample.application.port.FeeAccrualPort;
import com.example.sample.application.port.FeeSchedulePort;
import com.example.sample.domain.document.FeeAccrualDoc;
import com.example.sample.domain.document.FeeScheduleDoc;
import java.math.BigDecimal;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class FeeService {

    private final FeeAccrualPort accruals;
    private final FeeSchedulePort schedules;
    private final FeeCalculator calculator;

    public FeeService(FeeAccrualPort accruals, FeeSchedulePort schedules, FeeCalculator calculator) {
        this.accruals = accruals;
        this.schedules = schedules;
        this.calculator = calculator;
    }

    public FeeSummary summarise(String accountRef, String periodKey) {
        BigDecimal total = accruals.findForPeriod(accountRef, periodKey).stream()
                .map(FeeAccrualDoc::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
        return new FeeSummary(accountRef, periodKey, total);
    }

    public FeeSummary accrue(String accountRef, String periodKey, String scheduleId, BigDecimal balance) {
        FeeScheduleDoc schedule = schedules.findSchedule(scheduleId)
                .orElseThrow(() -> new IllegalArgumentException("unknown fee schedule"));
        BigDecimal fee = calculator.calculateFee(balance, schedule.rate());
        String id = UUID.randomUUID().toString();
        accruals.save(new FeeAccrualDoc(id, accountRef, periodKey, scheduleId, fee));
        return new FeeSummary(accountRef, periodKey, fee);
    }
}
