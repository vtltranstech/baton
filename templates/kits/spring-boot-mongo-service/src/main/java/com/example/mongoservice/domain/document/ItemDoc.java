package com.example.mongoservice.domain.document;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.index.Indexed;
import org.springframework.data.mongodb.core.mapping.Document;

/** Persistence shape. The natural key is itemKey (indexed, unique); id is a surrogate and never a business key. */
@Document(collection = "items")
public record ItemDoc(@Id String id, @Indexed(unique = true) String itemKey, String text) {
}
