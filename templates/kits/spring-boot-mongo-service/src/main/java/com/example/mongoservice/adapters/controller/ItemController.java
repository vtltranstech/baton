package com.example.mongoservice.adapters.controller;

import com.example.mongoservice.application.dto.ItemView;
import com.example.mongoservice.application.dto.NewItem;
import com.example.mongoservice.application.service.ItemService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** Validates, calls one service method, returns the DTO. No branch, loop or arithmetic here (PMD NoLogicInController). */
@RestController
@RequestMapping("/api/v1/items")
public class ItemController {

    private final ItemService items;

    public ItemController(ItemService items) {
        this.items = items;
    }

    @GetMapping("/{itemKey}")
    public ItemView read(@PathVariable String itemKey) {
        return items.read(itemKey);
    }

    @PutMapping
    public ItemView save(@Valid @RequestBody NewItem item) {
        return items.save(item);
    }
}
