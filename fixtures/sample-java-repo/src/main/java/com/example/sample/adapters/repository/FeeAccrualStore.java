package com.example.sample.adapters.repository;

import com.example.sample.application.port.FeeAccrualPort;
import com.example.sample.domain.document.FeeAccrualDoc;
import java.util.List;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Repository;

@Repository
public class FeeAccrualStore implements FeeAccrualPort {

    private final MongoTemplate mongo;

    public FeeAccrualStore(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    @Override
    public List<FeeAccrualDoc> findForPeriod(String accountRef, String periodKey) {
        Query query = new Query(Criteria.where("accountRef").is(accountRef).and("periodKey").is(periodKey));
        return mongo.find(query, FeeAccrualDoc.class, "fee_accruals");
    }

    @Override
    public void save(FeeAccrualDoc accrual) {
        mongo.insert(accrual, "fee_accruals");
    }
}
