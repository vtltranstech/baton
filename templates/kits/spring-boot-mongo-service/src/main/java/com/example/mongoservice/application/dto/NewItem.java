package com.example.mongoservice.application.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record NewItem(@NotBlank @Size(max = 64) String itemKey, @NotBlank @Size(max = 2000) String text) {
}
