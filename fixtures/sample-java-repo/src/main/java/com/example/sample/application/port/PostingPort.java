package com.example.sample.application.port;

import com.example.sample.application.dto.FeeSummary;

public interface PostingPort {

    void post(FeeSummary summary);
}
