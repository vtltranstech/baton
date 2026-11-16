package com.example.samplegradle.adapters.repository;

import com.example.samplegradle.domain.document.NoteDoc;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface NoteRepository extends MongoRepository<NoteDoc, String> {
}
