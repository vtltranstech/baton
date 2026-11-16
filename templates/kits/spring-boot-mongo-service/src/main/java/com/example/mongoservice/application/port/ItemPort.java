package com.example.mongoservice.application.port;

import com.example.mongoservice.domain.document.ItemDoc;
import java.util.Optional;

public interface ItemPort {

    Optional<ItemDoc> findByKey(String itemKey);

    ItemDoc save(ItemDoc item);
}
