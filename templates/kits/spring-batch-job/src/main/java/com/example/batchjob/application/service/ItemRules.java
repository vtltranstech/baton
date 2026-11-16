package com.example.batchjob.application.service;

import com.example.batchjob.application.dto.ItemLine;
import java.util.Locale;
import java.util.Optional;
import org.springframework.stereotype.Service;

/** The business rules of the job live here, once; the processor only calls them. */
@Service
public class ItemRules {

    /** A line without a key or text is dropped; the key is normalised, the text trimmed. */
    public Optional<ItemLine> normalise(ItemLine line) {
        if (isBlank(line.itemKey()) || isBlank(line.text())) {
            return Optional.empty();
        }
        return Optional.of(new ItemLine(line.itemKey().trim().toUpperCase(Locale.ROOT), line.text().trim()));
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}
