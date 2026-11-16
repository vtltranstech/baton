package com.example.batchjob.adapters.batch;

import com.example.batchjob.application.dto.ItemLine;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.launch.support.RunIdIncrementer;
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

/** Reader, processor and writer strictly separated. The writer replaces its output, so a rerun does not duplicate. */
@Configuration
public class ItemImportJobConfig {

    private static final int CHUNK_SIZE = 100; // <chunk size, from capacity.md>
    private static final String[] FIELDS = {"itemKey", "text"};

    @Bean
    public FlatFileItemReader<ItemLine> itemReader(@Value("${items.inbound-file}") String inboundFile) {
        return new FlatFileItemReaderBuilder<ItemLine>()
                .name("itemReader")
                .resource(new FileSystemResource(inboundFile))
                .linesToSkip(1)
                .delimited()
                .names(FIELDS)
                .targetType(ItemLine.class)
                .build();
    }

    @Bean
    public FlatFileItemWriter<ItemLine> itemWriter(@Value("${items.outbound-file}") String outboundFile) {
        return new FlatFileItemWriterBuilder<ItemLine>()
                .name("itemWriter")
                .resource(new FileSystemResource(outboundFile))
                .shouldDeleteIfExists(true)
                .delimited()
                .sourceType(ItemLine.class)
                .names(FIELDS)
                .build();
    }

    @Bean
    public Step itemImportStep(JobRepository jobRepository, PlatformTransactionManager transactionManager,
            FlatFileItemReader<ItemLine> itemReader, ItemLineProcessor processor, FlatFileItemWriter<ItemLine> itemWriter) {
        return new StepBuilder("itemImportStep", jobRepository)
                .<ItemLine, ItemLine>chunk(CHUNK_SIZE, transactionManager)
                .reader(itemReader)
                .processor(processor)
                .writer(itemWriter)
                .listener(new StepCountListener())
                .build();
    }

    @Bean
    public Job itemImportJob(JobRepository jobRepository, Step itemImportStep) {
        return new JobBuilder("itemImportJob", jobRepository)
                .incrementer(new RunIdIncrementer())
                .start(itemImportStep)
                .build();
    }
}
