package com.example.mongoservice.application.service;

import com.example.mongoservice.application.dto.ItemView;
import com.example.mongoservice.application.dto.NewItem;
import com.example.mongoservice.application.port.ItemPort;
import com.example.mongoservice.domain.ItemNotFoundException;
import com.example.mongoservice.domain.document.ItemDoc;
import org.springframework.stereotype.Service;

@Service
public class ItemService {

    private final ItemPort items;

    public ItemService(ItemPort items) {
        this.items = items;
    }

    public ItemView read(String itemKey) {
        return items.findByKey(itemKey)
                .map(ItemService::toView)
                .orElseThrow(() -> new ItemNotFoundException(itemKey));
    }

    /** Upsert on the natural key: a repeated create keeps one document per itemKey. */
    public ItemView save(NewItem item) {
        String id = items.findByKey(item.itemKey()).map(ItemDoc::id).orElse(null);
        return toView(items.save(new ItemDoc(id, item.itemKey(), item.text().trim())));
    }

    private static ItemView toView(ItemDoc doc) {
        return new ItemView(doc.itemKey(), doc.text());
    }
}
