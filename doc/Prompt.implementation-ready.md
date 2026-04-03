# Review Summary

- The original spec defines the main stack clearly but leaves several implementation-critical decisions implicit, especially around Doris table definitions, `ROUTINE LOAD` behavior, dbt materializations, and how services coordinate at startup.
- Naming is mostly fixed, but one section refers to `ods.bronze_events` while the naming rules define `dwh.bronze_events`. This creates avoidable confusion for the optional Iceberg sink.
- The spec requires rerun-safe gold models but does not state whether dbt models should be views or tables, whether raw data is append-only, or how metric windows should be recomputed.
- The Redpanda and Doris integration is underspecified for a local demo. Topic partition count, consumer settings, malformed record handling, and initial table schema choices need deterministic defaults.
- The producer supports schema evolution, but the raw ingestion design does not fully define how unknown fields are preserved for debugging and downstream compatibility.
- The optional Iceberg section mixes preferred guidance and hard requirements. It needs a smaller fixed scope so it can be implemented or deferred without affecting phase 1 acceptance.
- Repository structure is fixed, but execution ownership is unclear for SQL bootstrap steps, dbt runs, and optional batch jobs. The implementation path should state exactly what starts automatically and what is manual.

# Rewritten Specification

## 1. Project Goal

Build a local-first modern data stack demo with Docker Compose. The demo must show an end-to-end pipeline from event production to warehouse ingestion and warehouse transformations. Optional historical storage on Iceberg may be added only after the mandatory pipeline works.

The implementation target is a working local demo, not a production architecture.

## 2. Scope

### 2.1 Mandatory Scope

- Generate fake ecommerce events with a Python producer.
- Publish events to Redpanda topic `ecommerce_events`.
- Ingest events from Redpanda into Apache Doris with `ROUTINE LOAD`.
- Build bronze, silver, and gold models in Doris with `dbt-doris`.
- Deduplicate silver records by `event_id`.
- Ensure gold models are rerun-safe and do not double count when dbt runs multiple times against the same source data.
- Provide a README with exact setup, verification, and troubleshooting steps.

### 2.2 Optional Scope

- Add Iceberg table support backed by MinIO.
- Add a batch job that copies incremental windows from Doris to Iceberg with checkpointing.

### 2.3 Out of Scope

- AI agents
- CrewAI
- LangGraph
- Flink
- Spark
- anomaly detection
- RCA automation
- auto-remediation

## 3. Fixed Architecture

### 3.1 Required Components

- Event producer: Python
- Message broker: Redpanda
- Warehouse and query engine: Apache Doris
- Transformation layer: dbt with `dbt-doris`
- Object storage: MinIO
- Historical storage: Apache Iceberg on MinIO if optional scope is implemented

### 3.2 Required Data Flow

`producer -> redpanda:ecommerce_events -> ods.raw_ecommerce_events -> dwh.bronze_events -> dwh.silver_events -> analytics.gold_*`

Optional flow:

`dwh.bronze_events -> jobs/optional_iceberg_sink.py -> lakehouse.raw_events`

### 3.3 Simplicity Rule

Choose the smallest solution that works locally. Do not add orchestration frameworks, stream processors, or extra databases beyond the components listed above.

## 4. Repository Layout

Use this repository structure:

```text
.
├── docker-compose.yml
├── README.md
├── .env.example
├── sql/
│   ├── 01_create_databases.sql
│   ├── 02_create_ods_tables.sql
│   ├── 03_create_routine_load.sql
│   ├── 04_optional_iceberg.sql
│   └── 05_meta_checkpoint.sql
├── producer/
│   ├── requirements.txt
│   ├── producer.py
│   └── schemas/
│       └── ecommerce_event.example.json
├── dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml.example
│   ├── models/
│   │   ├── bronze/
│   │   │   └── bronze_events.sql
│   │   ├── silver/
│   │   │   └── silver_events.sql
│   │   └── gold/
│   │       ├── gold_revenue_per_minute.sql
│   │       ├── gold_order_cancellation_rate.sql
│   │       └── gold_conversion_funnel.sql
│   ├── tests/
│   │   └── schema.yml
│   └── macros/
│       └── grant_roles.sql
└── jobs/
    └── optional_iceberg_sink.py
```

Files related to Iceberg are optional and must be marked as optional in `README.md`.

## 5. Runtime Model

### 5.1 Docker Compose Services

Create these services:

- `redpanda`
- `minio`
- `doris-fe`
- `doris-be`
- `producer`
- `dbt-runner`

Optional:

- `jobs`

### 5.2 Startup Behavior

- `docker compose up -d` must start infrastructure services successfully.
- The producer may either auto-start with Compose or be runnable manually with a documented command. For a simpler demo, auto-start is preferred.
- SQL bootstrap is manual and documented in the README. Do not add an extra migration service unless required.
- dbt runs are manual and documented in the README.
- The optional Iceberg batch sink runs manually or in a simple loop inside the `jobs` container. Do not add Airflow, cron containers, or external schedulers.

### 5.3 Local Resource Assumptions

- Optimize for Docker Desktop on a developer laptop.
- Use small resource settings and low default throughput.
- Favor a single-node local setup for every service.

## 6. Redpanda Requirements

### 6.1 Topic

- Create topic `ecommerce_events`.
- Use `1` partition for the local demo.
- Use `1` replica where supported by the local Redpanda configuration.
- Configure retention conservatively for local disk usage. Default to a small time-based or size-based retention suitable for a demo.

### 6.2 Verification

The README must include commands to:

- verify the topic exists
- inspect recent messages
- confirm the producer is publishing continuously

## 7. Producer Requirements

### 7.1 Behavior

- Implement the producer in Python.
- Generate fake ecommerce events using `Faker`.
- Publish JSON messages continuously to topic `ecommerce_events`.
- Support publish rate configuration with an environment variable such as `EVENTS_PER_SECOND`.
- Support a schema evolution flag such as `ENABLE_SCHEMA_EVOLUTION=true` that adds optional fields to some events.

### 7.2 Required Event Schema

Every baseline event must include these fields:

- `event_id`
- `event_type`
- `event_time`
- `user_id`
- `session_id`
- `order_id`
- `product_id`
- `quantity`
- `price`
- `currency`
- `status`
- `payment_method`
- `device`
- `source`
- `ingested_at`

### 7.3 Event Types

The producer must generate at least:

- `page_view`
- `add_to_cart`
- `checkout_started`
- `order_created`
- `order_paid`
- `order_cancelled`

### 7.4 Schema Evolution

- Optional extra fields may include `campaign_id`, `voucher_code`, and `shipping_city`.
- Unknown fields must not break Redpanda publishing, Doris ingestion, dbt models, or the optional Iceberg sink.
- The producer should emit baseline fields on every event and only vary optional fields.

### 7.5 Demo-Oriented Data Rules

- `event_id` must be unique by default, with an optional mode that intentionally emits duplicates for validation.
- `event_time` and `ingested_at` must be ISO 8601 timestamps in UTC.
- `price` and `quantity` must be positive for purchase-related events unless an event type logically permits null or zero.

## 8. Doris Requirements

### 8.1 Databases

Create these databases:

- `ods`
- `dwh`
- `analytics`
- `meta`

If the optional Iceberg sink is implemented, also create or register `lakehouse` as needed by the chosen Doris Iceberg integration.

### 8.2 Raw Table

Create table `ods.raw_ecommerce_events` as the `ROUTINE LOAD` target.

The raw table must:

- store all baseline business fields required by downstream models
- include `ingested_at`
- include `raw_payload` as a string column for debugging and schema evolution tolerance
- remain append-only
- avoid business deduplication

### 8.3 Raw Table Column Strategy

Use explicit columns for all baseline fields and one additional `raw_payload` column containing the original JSON string when practical.

Unknown future JSON fields do not need dedicated columns in phase 1. Preserving the original payload is sufficient.

### 8.4 Routine Load

Create one `ROUTINE LOAD` job for topic `ecommerce_events`.

The load job must:

- parse required baseline fields into table columns
- tolerate unknown JSON fields
- avoid failing the entire job because of a small number of malformed records
- document all relevant load properties in SQL

For local-demo determinism, choose a permissive JSON ingestion configuration that ignores unmapped fields and keeps the job running when possible.

## 9. dbt Requirements

### 9.1 General Rules

- Use `dbt-doris`.
- Materialize bronze, silver, and gold as tables for deterministic local verification.
- Build models inside Doris using these names:
  - `dwh.bronze_events`
  - `dwh.silver_events`
  - `analytics.gold_revenue_per_minute`
  - `analytics.gold_order_cancellation_rate`
  - `analytics.gold_conversion_funnel`

### 9.2 Bronze Model

Create `bronze_events` with these responsibilities:

- select from `ods.raw_ecommerce_events`
- standardize column names
- cast timestamps into stable Doris-compatible types
- preserve source-level semantics
- expose `raw_payload`

Bronze should remain close to raw data and should not deduplicate.

### 9.3 Silver Model

Create `silver_events` with these responsibilities:

- enforce data types
- normalize enumerated values where needed
- handle null or malformed values conservatively
- deduplicate by `event_id`

Deduplication rule:

- if multiple rows share the same `event_id`, keep the row with the greatest `ingested_at`

### 9.4 Gold Models

Create these gold models:

- `gold_revenue_per_minute`
- `gold_order_cancellation_rate`
- `gold_conversion_funnel`

Definitions:

- `gold_revenue_per_minute`: aggregate revenue from paid order events by minute
- `gold_order_cancellation_rate`: aggregate cancelled orders divided by created orders by minute
- `gold_conversion_funnel`: aggregate counts by funnel step using `page_view`, `add_to_cart`, `checkout_started`, and `order_paid`

### 9.5 Rerun Safety

Rerun safety means:

- raw ingestion remains append-only
- silver deduplicates stable business keys
- gold models are rebuilt from current silver state and therefore do not accumulate duplicate metrics across repeated dbt runs

For the local demo, full-table rebuilds are acceptable. Incremental dbt models are not required.

## 10. dbt Tests

Add at least these tests:

- `not_null` on `event_id`
- `not_null` on `event_time`
- `accepted_values` on `event_type`
- `accepted_values` on `status`
- `unique` on `silver_events.event_id`

If Doris adapter limitations affect a test, document the limitation and use the closest practical alternative.

## 11. dbt Macro

Create macro `grant_roles.sql` that applies pragmatic demo permissions after dbt runs.

Minimum role intent:

- one read-only role for analytics consumers
- one broader role for engineers

The exact SQL may be simplified for local demo use.

## 12. Optional Iceberg Integration

### 12.1 Phase 1 Optional Rule

Iceberg is optional. Do not block mandatory scope on Iceberg work.

### 12.2 Fixed Optional Design

If implemented, use:

- source table: `dwh.bronze_events`
- target table: `lakehouse.raw_events`
- watermark column: `ingested_at`
- file format: Parquet
- table format: Iceberg V2
- partitioning: `day(ingested_at)`

### 12.3 Checkpoint Table

Create `meta.batch_job_checkpoint` with at least:

- `job_name`
- `source_table`
- `target_table`
- `last_success_start`
- `last_success_end`
- `status`
- `row_count`
- `updated_at`

### 12.4 Batch Sink Behavior

Implement `jobs/optional_iceberg_sink.py` as a simple periodic batch process:

1. Read the last successful checkpoint.
2. Compute the next closed window using `ingested_at`.
3. Read source rows from `dwh.bronze_events` for that window.
4. Write the window to `lakehouse.raw_events`.
5. Advance the checkpoint only after a successful write.

### 12.5 Idempotency

For the local demo, the sink may treat `dwh.bronze_events` as append-only raw history. Appending one successful closed window at a time is acceptable if checkpoint advancement is strictly post-write.

If the same window may be replayed, implement one of these deterministic strategies:

- overwrite the target partition for that window
- record a `batch_id` and ensure duplicate replays are detectable

Choose the simpler option supported by the implementation path.

### 12.6 Failure Rules

- If source query fails, do not update the checkpoint.
- If target write fails, do not update the checkpoint.
- Unknown JSON fields must not crash the sink.

## 13. Naming Rules

Use these names exactly unless a technical limitation requires a change:

- Redpanda topic: `ecommerce_events`
- Raw Doris table: `ods.raw_ecommerce_events`
- Bronze model: `dwh.bronze_events`
- Silver model: `dwh.silver_events`
- Gold tables: `analytics.gold_revenue_per_minute`, `analytics.gold_order_cancellation_rate`, `analytics.gold_conversion_funnel`
- Checkpoint table: `meta.batch_job_checkpoint`
- Optional Iceberg target: `lakehouse.raw_events`

If any name changes, document the reason and the final name in `README.md`.

## 14. README Requirements

`README.md` must include:

1. Project overview
2. Text-based architecture diagram
3. Prerequisites
4. Exact commands to start Docker Compose
5. Exact commands to verify Redpanda topic creation and message flow
6. Exact commands to run or verify the producer
7. Exact commands to create Doris databases, tables, and `ROUTINE LOAD`
8. Exact commands to run dbt models and tests
9. Example queries to inspect bronze, silver, and gold outputs
10. Procedure to test schema evolution
11. Procedure to test rerun safety
12. If implemented, procedure to run and verify the Iceberg sink
13. Known limitations
14. TODO items for any optional work not implemented

## 15. Acceptance Criteria

The implementation is complete when all mandatory items below are true:

1. `docker compose up -d` starts the required services successfully.
2. The producer publishes events to `ecommerce_events`.
3. Doris ingests events from Redpanda into `ods.raw_ecommerce_events` using `ROUTINE LOAD`.
4. dbt builds bronze, silver, and gold models successfully.
5. `dwh.silver_events` contains only one row per `event_id`.
6. `analytics.gold_revenue_per_minute` returns revenue aggregated by minute.
7. `analytics.gold_order_cancellation_rate` returns cancellation metrics derived from source events.
8. `analytics.gold_conversion_funnel` returns funnel counts for the required event types.
9. Adding new JSON fields in the producer does not crash ingestion or dbt runs.
10. Re-running dbt does not duplicate gold metrics.
11. `README.md` contains working setup and verification steps.

Optional completion criteria:

1. `lakehouse.raw_events` can be created on MinIO-backed Iceberg storage.
2. The batch sink writes at least one successful incremental window to Iceberg.
3. `meta.batch_job_checkpoint` advances only after successful writes and supports restart from the last successful window.

# Implementation Constraints

- Prioritize a working local demo over completeness.
- Keep the stack limited to Docker Compose, Python, Redpanda, Doris, dbt-doris, MinIO, and optional Iceberg.
- Do not add Flink, Spark, Airflow, LangGraph, CrewAI, or any other extra platform component.
- Keep the pipeline local-first and single-node.
- Use deterministic names defined in this specification.
- Prefer manual bootstrap steps documented in the README over adding more containers or automation layers.
- Preserve raw payload data for debugging and schema evolution tolerance.
- Keep raw ingestion append-only.
- Implement silver deduplication only in dbt, not in the raw ingestion layer.
- Materialize dbt models as tables for simple local verification.
- Make every mandatory step testable with explicit commands in the README.
- If optional Iceberg work is incomplete, leave it out of the runnable path and document it clearly as optional or TODO.

# Open Questions or Assumptions

- Assumption: Full-refresh dbt table builds are acceptable for phase 1 and are the default approach for rerun-safe local verification.
- Assumption: Unknown JSON fields are preserved through `raw_payload` rather than mapped into new Doris columns during phase 1.
- Assumption: The producer may auto-start in Docker Compose because this is the simplest path for a local demo.
