package com.example.batchjob.application.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.example.batchjob.application.dto.ItemLine;
import org.junit.jupiter.api.Test;

class ItemRulesTest {

    private final ItemRules rules = new ItemRules();

    @Test
    void keyIsNormalisedAndTextTrimmed() {
        assertEquals(new ItemLine("K1", "hello"), rules.normalise(new ItemLine(" k1 ", " hello ")).orElseThrow());
    }

    @Test
    void lineWithoutKeyIsDropped() {
        assertTrue(rules.normalise(new ItemLine(" ", "hello")).isEmpty());
    }

    @Test
    void lineWithoutTextIsDropped() {
        assertTrue(rules.normalise(new ItemLine("k1", null)).isEmpty());
    }
}
