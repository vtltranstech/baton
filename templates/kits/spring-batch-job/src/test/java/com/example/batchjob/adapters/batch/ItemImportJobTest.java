package com.example.batchjob.adapters.batch;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBatchTest
@SpringBootTest(properties = {
    "spring.batch.job.enabled=false",
    "items.inbound-file=src/test/resources/items-in.csv",
    "items.outbound-file=target/test-output/items-out.csv"
})
class ItemImportJobTest {

    private static final Path OUTPUT = Path.of("target/test-output/items-out.csv");

    private final JobLauncherTestUtils jobs;

    @Autowired
    ItemImportJobTest(JobLauncherTestUtils jobs) {
        this.jobs = jobs;
    }

    @Test
    void writesTheValidLinesAndCountsTheDroppedOnes() throws Exception {
        JobExecution run = jobs.launchJob();
        assertEquals(BatchStatus.COMPLETED, run.getStatus());
        StepExecution step = run.getStepExecutions().iterator().next();
        assertEquals(4, step.getReadCount());
        assertEquals(2, step.getFilterCount());
        assertEquals(List.of("K1,first", "K2,second"), Files.readAllLines(OUTPUT));
    }

    @Test
    void aRerunDoesNotDuplicateTheOutput() throws Exception {
        jobs.launchJob();
        jobs.launchJob();
        assertEquals(List.of("K1,first", "K2,second"), Files.readAllLines(OUTPUT));
    }
}
