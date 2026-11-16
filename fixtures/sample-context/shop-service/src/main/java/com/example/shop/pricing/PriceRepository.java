package com.example.shop.pricing;

import java.util.List;
import org.springframework.data.mongodb.repository.MongoRepository;
import org.springframework.data.mongodb.repository.Query;

public interface PriceRepository extends MongoRepository<PriceDoc, String> {

    @Query("{ 'status': 'ACTIVE', 'currencyCode': ?0 }")
    List<PriceDoc> active(String currencyCode);
}
