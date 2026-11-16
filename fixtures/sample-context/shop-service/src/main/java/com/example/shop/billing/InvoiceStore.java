package com.example.shop.billing;

import org.springframework.data.mongodb.core.MongoTemplate;

public class InvoiceStore {

    private final MongoTemplate mongo;

    public InvoiceStore(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    public void save(Invoice invoice) {
        mongo.save(invoice, "invoices");
    }
}
