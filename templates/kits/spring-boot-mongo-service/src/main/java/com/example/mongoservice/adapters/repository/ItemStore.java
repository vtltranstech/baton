package com.example.mongoservice.adapters.repository;

import com.example.mongoservice.application.port.ItemPort;
import com.example.mongoservice.domain.document.ItemDoc;
import java.util.Optional;
import org.springframework.stereotype.Component;

@Component
public class ItemStore implements ItemPort {

    private final ItemRepository repository;

    public ItemStore(ItemRepository repository) {
        this.repository = repository;
    }

    @Override
    public Optional<ItemDoc> findByKey(String itemKey) {
        return repository.findByItemKey(itemKey);
    }

    @Override
    public ItemDoc save(ItemDoc item) {
        return repository.save(item);
    }
}
