package com.example.mongoservice.application.dto;

/** API shape. Persistence types never cross the API boundary. */
public record ItemView(String itemKey, String text) {
}
