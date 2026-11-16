package com.example.sample.adapters.batch;

import com.example.sample.application.dto.FeeSummary;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.FlatFileItemWriter;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.batch.item.file.builder.FlatFileItemWriterBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class FeeAccrualJobConfig {

    private static final int CHUNK_SIZE = 100;

    @Bean
    public FlatFileItemReader<FeeSummary> balanceReader() {
        return new FlatFileItemReaderBuilder<FeeSummary>()
                .name("balanceReader")
                .resource(new FileSystemResource("/data/inbound/balances.csv"))
                .delimited()
                .names("accountRef", "periodKey", "total")
                .targetType(FeeSummary.class)
                .build();
    }

    @Bean
    public FlatFileItemWriter<FeeSummary> accrualWriter(@Value("${accrual.outbound-file}") String outboundFile) {
        return new FlatFileItemWriterBuilder<FeeSummary>()
                .name("accrualWriter")
                .resource(new FileSystemResource(outboundFile))
                .delimited()
                .names("accountRef", "periodKey", "total")
                .build();
    }

    @Bean
    public Step accrualStep(JobRepository jobRepository, PlatformTransactionManager transactionManager,
            FlatFileItemReader<FeeSummary> balanceReader, FlatFileItemWriter<FeeSummary> accrualWriter) {
        return new StepBuilder("accrualStep", jobRepository)
                .<FeeSummary, FeeSummary>chunk(CHUNK_SIZE, transactionManager)
                .reader(balanceReader)
                .writer(accrualWriter)
                .build();
    }

    @Bean
    public Job feeAccrualJob(JobRepository jobRepository, Step accrualStep) {
        return new JobBuilder("feeAccrualJob", jobRepository).start(accrualStep).build();
    }
}
