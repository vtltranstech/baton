package com.example.samplegradle.domain.document;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "notes")
public record NoteDoc(@Id String id, String text) {
}
