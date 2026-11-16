package com.example.mongoservice.adapters.controller;

import com.example.mongoservice.domain.ItemNotFoundException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

/** Domain exceptions become RFC 9457 problem details at the edge, and only here. */
@RestControllerAdvice
public class ProblemMapping {

    @ExceptionHandler(ItemNotFoundException.class)
    public ProblemDetail notFound(ItemNotFoundException e) {
        return ProblemDetail.forStatusAndDetail(HttpStatus.NOT_FOUND, e.getMessage());
    }
}
