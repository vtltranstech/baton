package com.example.samplegradle.adapters.repository;

import com.example.samplegradle.application.port.NotePort;
import com.example.samplegradle.domain.document.NoteDoc;
import java.util.Optional;
import org.springframework.stereotype.Component;

@Component
public class NoteStore implements NotePort {

    private final NoteRepository repository;

    public NoteStore(NoteRepository repository) {
        this.repository = repository;
    }

    @Override
    public Optional<NoteDoc> findNote(String id) {
        return repository.findById(id);
    }
}
