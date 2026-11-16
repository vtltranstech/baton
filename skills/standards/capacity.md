# Capacity - the numbers come first, then the technology

The team states the numbers; the design derives the choice from them. Values below are starting points, not benchmarks: a design that relies on one says how it will be measured. A project overrides them in `profile/domain.md`.

## What to ask (the `## Capacity` section of a story; only the rows that apply)
| Applies to | Ask |
| --- | --- |
| API | peak requests per second, average and peak; target p95 latency; largest request and response; slowest downstream call |
| File or batch | largest file (MB/GB) and record count; how often; the time window it must finish in; must a failed run resume; format |
| Messaging | peak messages per second; largest message; can it be replayed; does order matter |
| Data | documents now and growth per year; largest document; reads vs writes |

A number nobody knows is written `unknown`, with who will find out. It is never filled in by an agent. The architect may design on a stated assumption, marked `assumed`, which caps design confidence at 74 and goes under "Reviewer should check".

## File and batch
| When | Use | Not |
| --- | --- | --- |
| One-off or small, fits in memory comfortably, a failed run can simply rerun | a plain service method that streams | Spring Batch: its job tables and config buy nothing here |
| Recurring, or must resume after failure, or needs skip/retry per record, or roughly over 100k records, or larger than the heap | **Spring Batch**, chunk-oriented, with a streaming reader (`FlatFileItemReader`, `StaxEventItemReader`) | reading the whole file into a list, a DOM or `readTree` |
| Spring Batch still misses the window when measured | partitioned step, then tune chunk size by measurement | adding threads to a stateful reader, which is not thread-safe |
| Records arrive continuously | a consumer on the topic or queue | a polling batch |
| Beyond what one service can process in the window | stop: this is an open decision for the Tech Lead | choosing a new platform in a design note |

File size alone does not decide. Restart, skip and the time window usually matter more. Spring Batch needs a job repository: if the service has none, say which store and treat it as a new dependency.

## API
Concurrent requests = requests per second x latency in seconds. 200 rps at 250 ms is 50 in flight. Size thread and connection pools from this, for peak.

| When | Use | Not |
| --- | --- | --- |
| Default | Spring MVC, default pool sized from the formula | WebFlux because the number sounds big |
| Blocking I/O, concurrency above the thread pool, Java 21 or later | virtual threads (`spring.threads.virtual.enabled=true`), with the database and HTTP pools still bounded | an unbounded pool that moves the queue to the database |
| The service is already reactive, or it streams to many slow clients | WebFlux | mixing blocking calls into a reactive chain |
| The work takes longer than a client should wait | `202 Accepted` plus a job and a status endpoint | a long synchronous call |
| A large list or payload | pagination or streaming, with a maximum page size | returning an unbounded list |

Every outbound call has a connect and a read timeout. A retry needs an idempotent target. Add a circuit breaker when a slow downstream could use up the pool. Every query on a hot path names its index. A cache needs a measured hot path, per `patterns.md`.

## Messaging and data
- Partitions >= peak messages per second / what one consumer handled when measured. Order holds only within a partition, so the key follows what must stay in order.
- Bulk writes for batches. A document that grows without limit is a design finding. Every new query names its index and the data volume it was checked at.

## Design note: Capacity and technology choice
| Fact (from the story) | Value | stated or assumed | What it decided | Rejected alternative, and why | How it is measured |
| --- | --- | --- | --- | --- | --- |

Then list the configuration it implies, with values: chunk size, pool sizes, timeouts, indexes, partitions. A value with no measurement behind it is labelled `initial`.

## Proof
A number in an AC is verified by running it, per the `data-check` skill: state the data size and environment. If the test environment cannot show it, QA writes `Performance not measured: <why>` and the human at gate 3 decides. A capacity claim with no measurement is never reported as met.
