package com.example.mongoservice.adapters.repository;

import com.example.mongoservice.domain.document.ItemDoc;
import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ItemRepository extends MongoRepository<ItemDoc, String> {

    Optional<ItemDoc> findByItemKey(String itemKey);
}
