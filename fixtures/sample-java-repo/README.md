# sample-java-repo

A tiny Spring Boot 3 + Mongo + Kafka + JMS + Batch app, clean on every sensor. Build: `./mvnw -q verify` (JDK 21; on JDK 17 add `-Djava.version=17`).

- `EXPECTED.json`: the planted edges, collections, aggregates, layout and stack facts, the acceptance list for the extractors.
- `violations/`: one patch per planted violation, plus `MANIFEST.json` naming the sensor and report that must catch it. A directory in the baton repo cannot have its own git branch, so patches stand in for a violations branch.
- `variants/gradle-kts/`: a separate small repo, built with Gradle Kotlin DSL on Java 17. Treat it as its own repo, not as source of this one.
- `config/sensors/`: copies of the baton `sensors/` files, plus this repo's `pmd-extra.xml` (the period-key rule); a test keeps the copies identical.
