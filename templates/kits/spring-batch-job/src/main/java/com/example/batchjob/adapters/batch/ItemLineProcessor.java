package com.example.batchjob.adapters.batch;

import com.example.batchjob.application.dto.ItemLine;
import com.example.batchjob.application.service.ItemRules;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.stereotype.Component;

/** A pure function of one item. Returning null filters the item (counted as filtered by the step). */
@Component
public class ItemLineProcessor implements ItemProcessor<ItemLine, ItemLine> {

    private final ItemRules rules;

    public ItemLineProcessor(ItemRules rules) {
        this.rules = rules;
    }

    @Override
    public ItemLine process(ItemLine line) {
        return rules.normalise(line).orElse(null);
    }
}
