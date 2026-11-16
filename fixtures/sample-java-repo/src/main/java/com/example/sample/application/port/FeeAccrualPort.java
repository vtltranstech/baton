package com.example.sample.application.port;

import com.example.sample.domain.document.FeeAccrualDoc;
import java.util.List;

public interface FeeAccrualPort {

    List<FeeAccrualDoc> findForPeriod(String accountRef, String periodKey);

    void save(FeeAccrualDoc accrual);
}
