package com.example.samplegradle.application.service;

import com.example.samplegradle.application.dto.NoteView;
import com.example.samplegradle.application.port.NotePort;
import org.springframework.stereotype.Service;

@Service
public class NoteService {

    private final NotePort notes;

    public NoteService(NotePort notes) {
        this.notes = notes;
    }

    public NoteView read(String id) {
        return notes.findNote(id)
                .map(note -> new NoteView(note.id(), note.text().trim()))
                .orElseThrow(() -> new IllegalArgumentException("unknown note"));
    }
}
