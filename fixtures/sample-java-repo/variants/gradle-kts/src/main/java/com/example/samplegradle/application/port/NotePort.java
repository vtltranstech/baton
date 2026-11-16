package com.example.samplegradle.application.port;

import com.example.samplegradle.domain.document.NoteDoc;
import java.util.Optional;

public interface NotePort {

    Optional<NoteDoc> findNote(String id);
}
