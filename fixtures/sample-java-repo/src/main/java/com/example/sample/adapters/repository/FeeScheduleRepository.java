package com.example.sample.adapters.repository;

import com.example.sample.domain.document.FeeScheduleDoc;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface FeeScheduleRepository extends MongoRepository<FeeScheduleDoc, String> {
}
