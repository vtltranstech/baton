package com.example.sample.application.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.example.sample.application.dto.FeeSummary;
import com.example.sample.application.port.FeeAccrualPort;
import com.example.sample.application.port.FeeSchedulePort;
import com.example.sample.domain.document.FeeAccrualDoc;
import com.example.sample.domain.document.FeeScheduleDoc;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class FeeServiceTest {

    private final List<FeeAccrualDoc> saved = new ArrayList<>();
    private final FeeAccrualPort accruals = new FeeAccrualPort() {
        @Override
        public List<FeeAccrualDoc> findForPeriod(String accountRef, String periodKey) {
            return saved;
        }

        @Override
        public void save(FeeAccrualDoc accrual) {
            saved.add(accrual);
        }
    };
    private final FeeSchedulePort schedules = scheduleId -> "s1".equals(scheduleId)
            ? Optional.of(new FeeScheduleDoc("s1", "standard", new BigDecimal("0.10")))
            : Optional.empty();
    private final FeeService service = new FeeService(accruals, schedules, new FeeCalculator());

    @Test
    void accrueStoresTheCalculatedFee() {
        FeeSummary summary = service.accrue("a1", "2026-11", "s1", new BigDecimal("100.00"));
        assertEquals(new BigDecimal("10.00"), summary.total());
        assertEquals(new BigDecimal("10.00"), saved.get(0).amount());
    }

    @Test
    void summaryAddsTheAccrualsOfThePeriod() {
        service.accrue("a1", "2026-11", "s1", new BigDecimal("100.00"));
        service.accrue("a1", "2026-11", "s1", new BigDecimal("200.00"));
        assertEquals(new BigDecimal("30.00"), service.summarise("a1", "2026-11").total());
    }

    @Test
    void unknownScheduleIsRefused() {
        assertThrows(IllegalArgumentException.class,
                () -> service.accrue("a1", "2026-11", "nope", BigDecimal.ONE));
    }
}
