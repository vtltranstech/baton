package com.example.mongoservice.application.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.example.mongoservice.application.dto.NewItem;
import com.example.mongoservice.application.port.ItemPort;
import com.example.mongoservice.domain.ItemNotFoundException;
import com.example.mongoservice.domain.document.ItemDoc;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class ItemServiceTest {

    private final Map<String, ItemDoc> stored = new HashMap<>();
    private final ItemPort port = new ItemPort() {
        @Override
        public Optional<ItemDoc> findByKey(String itemKey) {
            return Optional.ofNullable(stored.get(itemKey));
        }

        @Override
        public ItemDoc save(ItemDoc item) {
            ItemDoc saved = new ItemDoc(item.id() == null ? "id-" + item.itemKey() : item.id(), item.itemKey(), item.text());
            stored.put(saved.itemKey(), saved);
            return saved;
        }
    };
    private final ItemService service = new ItemService(port);

    @Test
    void readReturnsTheStoredItem() {
        stored.put("k1", new ItemDoc("id1", "k1", "hello"));
        assertEquals("hello", service.read("k1").text());
    }

    @Test
    void unknownItemIsRefused() {
        assertThrows(ItemNotFoundException.class, () -> service.read("nope"));
    }

    @Test
    void saveTrimsTheText() {
        assertEquals("hello", service.save(new NewItem("k1", " hello ")).text());
    }

    @Test
    void savingTheSameKeyTwiceKeepsOneDocument() {
        service.save(new NewItem("k1", "first"));
        service.save(new NewItem("k1", "second"));
        assertEquals(1, stored.size());
        assertEquals("id-k1", stored.get("k1").id());
        assertEquals("second", service.read("k1").text());
    }
}
