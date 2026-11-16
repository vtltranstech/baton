package com.example.batchjob.adapters.batch;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

/** Records counts in, filtered, written and skipped per step; reconciliation reads them. Counts only, no identifiers. */
public class StepCountListener implements StepExecutionListener {

    private static final Logger log = LoggerFactory.getLogger(StepCountListener.class);

    @Override
    public ExitStatus afterStep(StepExecution step) {
        log.info("step={} read={} filtered={} written={} skipped={}", step.getStepName(), step.getReadCount(),
                step.getFilterCount(), step.getWriteCount(), step.getSkipCount());
        return step.getExitStatus();
    }
}
