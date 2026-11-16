package com.example.sample.application.port;

import com.example.sample.domain.document.FeeScheduleDoc;
import java.util.Optional;

public interface FeeSchedulePort {

    Optional<FeeScheduleDoc> findSchedule(String scheduleId);
}
