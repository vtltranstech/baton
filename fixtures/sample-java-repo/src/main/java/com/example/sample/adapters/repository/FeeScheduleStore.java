package com.example.sample.adapters.repository;

import com.example.sample.application.port.FeeSchedulePort;
import com.example.sample.domain.document.FeeScheduleDoc;
import java.util.Optional;
import org.springframework.stereotype.Component;

@Component
public class FeeScheduleStore implements FeeSchedulePort {

    private final FeeScheduleRepository repository;

    public FeeScheduleStore(FeeScheduleRepository repository) {
        this.repository = repository;
    }

    @Override
    public Optional<FeeScheduleDoc> findSchedule(String scheduleId) {
        return repository.findById(scheduleId);
    }
}
