package com.example.samplegradle.application.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.example.samplegradle.domain.document.NoteDoc;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class NoteServiceTest {

    private final NoteService service = new NoteService(
            id -> "n1".equals(id) ? Optional.of(new NoteDoc("n1", " hello ")) : Optional.empty());

    @Test
    void readTrimsTheText() {
        assertEquals("hello", service.read("n1").text());
    }

    @Test
    void unknownNoteIsRefused() {
        assertThrows(IllegalArgumentException.class, () -> service.read("nope"));
    }
}
