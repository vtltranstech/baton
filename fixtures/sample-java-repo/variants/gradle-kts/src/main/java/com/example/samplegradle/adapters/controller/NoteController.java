package com.example.samplegradle.adapters.controller;

import com.example.samplegradle.application.dto.NoteView;
import com.example.samplegradle.application.service.NoteService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class NoteController {

    private final NoteService notes;

    public NoteController(NoteService notes) {
        this.notes = notes;
    }

    @GetMapping("/api/v1/notes/{id}")
    public NoteView read(@PathVariable String id) {
        return notes.read(id);
    }
}
