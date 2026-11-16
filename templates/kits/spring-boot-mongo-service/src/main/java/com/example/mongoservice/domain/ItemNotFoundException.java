package com.example.mongoservice.domain;

public class ItemNotFoundException extends RuntimeException {

    private static final long serialVersionUID = 1L;

    public ItemNotFoundException(String itemKey) {
        super("no item with key " + itemKey);
    }
}
