package com.example.batchjob.application.dto;

/** One line of the inbound file. itemKey is the natural key: a rerun writes each key once. */
public record ItemLine(String itemKey, String text) {
}
