package com.example.mongoservice.adapters.controller;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.mongoservice.application.dto.ItemView;
import com.example.mongoservice.application.dto.NewItem;
import com.example.mongoservice.application.service.ItemService;
import com.example.mongoservice.domain.ItemNotFoundException;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@WebMvcTest(ItemController.class)
class ItemControllerTest {

    private final MockMvc mvc;

    @MockitoBean
    private ItemService items;

    @Autowired
    ItemControllerTest(MockMvc mvc) {
        this.mvc = mvc;
    }

    @Test
    void readReturnsTheView() throws Exception {
        when(items.read("k1")).thenReturn(new ItemView("k1", "hello"));
        mvc.perform(get("/api/v1/items/k1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.text").value("hello"));
    }

    @Test
    void unknownItemIsAProblemDetail404() throws Exception {
        when(items.read("nope")).thenThrow(new ItemNotFoundException("nope"));
        mvc.perform(get("/api/v1/items/nope"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404));
    }

    @Test
    void blankTextIsRejectedBeforeTheService() throws Exception {
        when(items.save(any(NewItem.class))).thenReturn(new ItemView("k1", "x"));
        mvc.perform(put("/api/v1/items").contentType(MediaType.APPLICATION_JSON)
                        .content("{\"itemKey\":\"k1\",\"text\":\" \"}"))
                .andExpect(status().isBadRequest());
    }
}
