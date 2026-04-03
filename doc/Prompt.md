# Review Summary

- The original spec defines the major components clearly, but several operational decisions are left open. A coding agent would still need to choose Doris schemas, dbt materializations, container startup flow, and verification commands.
- The naming is mostly consistent, but the Iceberg section refers to `ods.bronze_events` while the naming rules define `dwh.bronze_events`. This creates avoidable implementation drift.
- Rerun safety is required for silver and gold, but the spec does not fix how dbt should achieve it. Without a concrete rule, a coding agent could choose incompatible materializations.
- The Doris ingestion requirements are directionally correct but underspecified for a local demo. The spec does not fix whether unknown JSON fields are ignored via column mapping, whether malformed rows are tolerated via load properties, or how the raw table stores payload for debugging.
- The Docker Compose section lists required services but does not define startup ordering, health checks, or whether SQL/bootstrap steps run automatically or manually.
- The optional Iceberg path is conceptually defined, but the implementation boundary is vague. The spec does not fix the Iceberg catalog choice, the writer library, or whether the sink reads from Doris over SQLAlchemy, Arrow, or a native client.
- The README requirements are strong, but acceptance criteria do not require a deterministic verification sequence. This increases the risk of a demo that starts but is hard to validate.

# Rewritten Specification

## 1. Project Goal

Build a local-first modern data stack demo that runs on a single developer machine using Docker Compose.

The demo must show this end-to-end flow:

`Python producer -> Redpanda -> Apache Doris -> dbt bronze/silver/gold`

An optional phase 1 extension may also copy historical data from Doris into Iceberg tables stored in MinIO.

The implementation priority is:

1. Working local demo
2. Simple operations and debugging
3. Minimal components
4. Deterministic setup and verification
5. Architectural completeness only where required to satisfy the demo

## 2. Scope

### 2.1 Mandatory Scope

- A Python producer generates fake ecommerce JSON events continuously.
- Redpanda stores the events on topic `ecommerce_events`.
- Apache Doris consumes the topic with `ROUTINE LOAD` into a raw ingestion table.
- dbt builds `bronze`, `silver`, and `gold` models inside Doris.
- Silver deduplicates by `event_id`.
- Gold models are rerun-safe and must not double count when dbt is executed again.
- MinIO runs as local S3-compatible object storage even if Iceberg is not enabled in the first pass.
- README documents setup, execution, validation, and limitations.

### 2.2 Optional Scope

- Iceberg catalog and table creation on top of MinIO
- A batch job that copies historical data from Doris to Iceberg using checkpointed windows

### 2.3 Out of Scope

- AI agents
- CrewAI
- LangGraph
- Flink
- Spark
- Anomaly detection
- Root cause analysis automation
- Auto-remediation

## 3. Fixed Implementation Decisions

These decisions are mandatory unless a technical blocker makes them impossible.

### 3.1 Core Technologies

- Producer language: Python 3
- Message broker: Redpanda
- Analytical database and serving layer: Apache Doris
- Transformations: `dbt-core` with `dbt-doris`
- Object storage: MinIO
- Optional historical table format: Apache Iceberg

### 3.2 Local-First Rule

- The project must run entirely on a local machine with Docker Compose.
- Do not add orchestration systems, distributed compute engines, or extra databases.
- Prefer one-command startup and explicit manual verification steps over automation that introduces complexity.

### 3.3 Simplifying Assumptions

- Docker Desktop is the target runtime.
- Resource usage must stay modest enough for a local laptop.
- Single-node Redpanda and single FE/BE Doris deployment are sufficient.
- Small data volume is acceptable. This is a demo, not a benchmark.

## 4. Required Repository Layout

Create the repository with this structure:

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

Rules:

- All listed files must exist, even when optional features are not implemented yet.
- If Iceberg is not implemented, keep the optional files as stubs with a clear TODO note.
- File names and model names must match this specification exactly.

## 5. Runtime Architecture

### 5.1 Mandatory Services

Define these Docker Compose services:

- `redpanda`
- `minio`
- `doris-fe`
- `doris-be`
- `producer`
- `dbt-runner`

### 5.2 Optional Service

- `jobs` for the Iceberg batch sink

### 5.3 Service Rules

- Add health checks where practical for Doris FE, Doris BE, MinIO, and Redpanda.
- Use `depends_on` only to improve local startup order. Do not assume it guarantees readiness.
- Put runtime ports in `.env.example` where practical.
- Keep container configuration explicit and small.

## 6. End-to-End Data Flow

The mandatory data flow is:

1. `producer/producer.py` emits fake ecommerce events as JSON.
2. Events are published to Redpanda topic `ecommerce_events`.
3. Doris `ROUTINE LOAD` consumes the topic and writes rows into `ods.raw_ecommerce_events`.
4. dbt builds `dwh.bronze_events`.
5. dbt builds `dwh.silver_events`.
6. dbt builds gold models in `analytics`.

The optional data flow is:

1. The Iceberg sink reads a closed incremental window from `dwh.bronze_events`.
2. The sink writes that window to `lakehouse.raw_events` in MinIO-backed Iceberg storage.
3. The sink updates `meta.batch_job_checkpoint` only after a successful write.

## 7. Naming Rules

Use these names exactly:

- Redpanda topic: `ecommerce_events`
- Doris raw table: `ods.raw_ecommerce_events`
- dbt bronze model and table: `dwh.bronze_events`
- dbt silver model and table: `dwh.silver_events`
- Gold tables: `analytics.gold_revenue_per_minute`, `analytics.gold_order_cancellation_rate`, `analytics.gold_conversion_funnel`
- Checkpoint table: `meta.batch_job_checkpoint`
- Optional Iceberg table: `lakehouse.raw_events`

If a name must change due to a technical limitation, document the exact reason in `README.md`.

## 8. Redpanda Requirements

### 8.1 Topic Configuration

- Create topic `ecommerce_events`.
- Use `1` partition for the default local demo.
- Use a conservative retention configuration suitable for a laptop demo.

### 8.2 Verification Requirements

README must include commands to verify:

- The topic exists
- Messages are arriving
- The producer can reconnect after Redpanda startup

## 9. Producer Requirements

### 9.1 Behavior

Implement the producer in Python.

The producer must:

- Generate fake ecommerce events using `Faker`
- Publish continuously to `ecommerce_events`
- Support configurable publish rate via environment variable
- Support a schema-evolution mode that adds optional extra JSON fields
- Log basic send progress and errors to stdout

### 9.2 Required Event Schema

The baseline event payload must contain these fields:

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

### 9.3 Supported Event Types

The producer must emit at least:

- `page_view`
- `add_to_cart`
- `checkout_started`
- `order_created`
- `order_paid`
- `order_cancelled`

### 9.4 Schema Evolution

When schema-evolution mode is enabled, the producer may add fields such as:

- `campaign_id`
- `voucher_code`
- `shipping_city`

Rules:

- Extra fields must remain optional.
- Extra fields must not break Redpanda ingestion.
- Extra fields must not break Doris `ROUTINE LOAD`.
- Extra fields do not need to be modeled in bronze, silver, or gold for phase 1.

## 10. Doris Requirements

### 10.1 Databases

Create these Doris databases:

- `ods`
- `dwh`
- `analytics`
- `meta`

If the optional Iceberg path is implemented, also create or register:

- `lakehouse`

### 10.2 Raw Ingestion Table

Create `ods.raw_ecommerce_events` as the direct target of `ROUTINE LOAD`.

This table must include, at minimum:

- All baseline event fields needed by bronze
- `ingested_at`
- `raw_payload`

Design rules:

- Keep this layer close to source data.
- Do not perform business deduplication here.
- Preserve enough raw detail for debugging.
- Store `raw_payload` as the original JSON string when practical.

### 10.3 Routine Load Behavior

Create a single `ROUTINE LOAD` job that reads from topic `ecommerce_events`.

Requirements:

- Parse required JSON fields into typed columns
- Ignore unknown JSON fields
- Keep running when new optional fields appear
- Tolerate malformed rows where Doris supports this without stopping the whole job
- Document exact load properties in `sql/03_create_routine_load.sql`

Implementation rule for the local demo:

- Choose the simplest `ROUTINE LOAD` JSON mapping that works with extra fields ignored.
- If malformed-row tolerance is limited by Doris behavior, prefer a documented best-effort configuration over adding extra middleware.

## 11. dbt Requirements

### 11.1 General dbt Rules

- Use `dbt-core` with `dbt-doris`.
- Set model schemas so bronze and silver build in `dwh` and gold builds in `analytics`.
- Use deterministic SQL. Do not depend on non-repeatable logic.
- README must include exact commands for `dbt debug`, `dbt run`, and `dbt test`.

### 11.2 Bronze Model

Create `dwh.bronze_events`.

Purpose:

- Clean raw column names if needed
- Standardize timestamps into consistent Doris-compatible types
- Preserve raw business semantics
- Stay close to `ods.raw_ecommerce_events`

Materialization rule:

- Use a full-refresh-safe table model unless Doris constraints require a view.
- The bronze model does not perform deduplication.

### 11.3 Silver Model

Create `dwh.silver_events`.

Purpose:

- Deduplicate by `event_id`
- Enforce data types
- Normalize enumerated values where needed
- Handle null and malformed values conservatively

Deduplication rule:

- If multiple rows share the same `event_id`, keep the row with the latest `ingested_at`.

Rerun-safety rule:

- The model output must be deterministic when built multiple times from the same bronze input.

Materialization rule:

- Use a table model with deterministic deduplication SQL based on `row_number()` or equivalent Doris window logic.

### 11.4 Gold Models

Create these gold models:

- `analytics.gold_revenue_per_minute`
- `analytics.gold_order_cancellation_rate`
- `analytics.gold_conversion_funnel`

Definitions:

- `gold_revenue_per_minute`: aggregate paid revenue by minute using `order_paid` events
- `gold_order_cancellation_rate`: aggregate cancellation rate by minute or hour; choose one granularity and document it
- `gold_conversion_funnel`: aggregate counts and conversion ratios for `page_view -> add_to_cart -> checkout_started -> order_paid`

Rerun-safety rule:

- Gold outputs must be derived from stable bronze or silver inputs and must not accumulate duplicate rows when dbt is re-run.

Materialization rule:

- Use full-refresh-safe table models.
- Do not use append-only incremental logic for gold in phase 1.

## 12. dbt Tests

Add tests in `dbt/tests/schema.yml` for at least:

- `not_null` on `silver_events.event_id`
- `not_null` on `silver_events.event_time`
- `accepted_values` on `silver_events.event_type`
- `accepted_values` on `silver_events.status`
- `unique` on `silver_events.event_id`

If bronze tests are added, mark them as optional in the README.

## 13. dbt Macro

Create `macros/grant_roles.sql`.

The macro must support pragmatic demo-level grants for:

- A read-only analytics consumer role
- A broader engineer role

Rules:

- Keep the SQL simple.
- The macro may be a no-op on environments where Doris role DDL differs from expectations, but this must be documented.

## 14. Optional Iceberg Integration

This section is optional for phase 1. Complete it only after all mandatory scope works.

### 14.1 Goal

Copy historical data from Doris into an Iceberg table stored on MinIO.

### 14.2 Fixed Choices for Optional Implementation

- Source table: `dwh.bronze_events`
- Target table: `lakehouse.raw_events`
- Watermark column: `ingested_at`
- File format: Parquet
- Iceberg table format version: V2
- Partitioning: `day(ingested_at)`

### 14.3 Batch Sink Behavior

Implement `jobs/optional_iceberg_sink.py` as a simple loop or periodic job.

The job must:

1. Read the last successful checkpoint from `meta.batch_job_checkpoint`
2. Compute the next closed window using `ingested_at`
3. Read rows from `dwh.bronze_events` for that window
4. Write them to `lakehouse.raw_events`
5. Advance the checkpoint only after the write succeeds

### 14.4 Checkpoint Table

Create `meta.batch_job_checkpoint` with at least:

- `job_name`
- `source_table`
- `target_table`
- `last_success_start`
- `last_success_end`
- `status`
- `row_count`
- `updated_at`

### 14.5 Idempotency Rules

- For raw bronze data, append-only writes are acceptable.
- The checkpoint must advance only after a successful Iceberg write.
- Re-running a failed window must not skip data.
- Re-running a successful window may create duplicates only if the checkpoint is intentionally rolled back; document this limitation if it exists.

### 14.6 Failure Rules

- Query failure: do not update checkpoint
- Write failure: do not update checkpoint
- Unknown extra JSON fields: ignore them unless explicitly mapped into the Iceberg schema

### 14.7 Optional Implementation Boundary

For phase 1, the simplest acceptable implementation is:

- Doris query from Python
- Iceberg write using a Python library that works locally
- Minimal scheduler loop in Python

Do not add Flink or Spark to support this feature.

## 15. SQL Bootstrap Files

The SQL files must be organized as follows:

- `sql/01_create_databases.sql`: create Doris databases
- `sql/02_create_ods_tables.sql`: create `ods.raw_ecommerce_events`
- `sql/03_create_routine_load.sql`: create and start the `ROUTINE LOAD` job
- `sql/04_optional_iceberg.sql`: optional Iceberg DDL or catalog registration
- `sql/05_meta_checkpoint.sql`: create `meta.batch_job_checkpoint`

Rules:

- Files must be executable independently in order.
- Optional SQL must not block the mandatory demo path.

## 16. README Requirements

`README.md` must include:

1. Project overview
2. Text architecture diagram
3. Prerequisites
4. Environment configuration using `.env.example`
5. Docker Compose startup steps
6. How to verify Redpanda topic creation
7. How to run or validate the producer
8. How to create Doris databases, tables, and routine load job
9. How to run dbt
10. How to query bronze, silver, and gold outputs
11. How to test schema evolution
12. How to test rerun safety
13. If implemented, how to run and verify the Iceberg sink
14. Known limitations
15. TODO items for unfinished optional features

README must contain a deterministic validation sequence that a coding agent or reviewer can execute from top to bottom.

## 17. Acceptance Criteria

The project is complete when all mandatory items below are true:

1. `docker-compose.yml` starts the required services successfully on a local machine.
2. The producer publishes events to `ecommerce_events`.
3. Doris consumes those events with `ROUTINE LOAD`.
4. Rows appear in `ods.raw_ecommerce_events`.
5. dbt builds `dwh.bronze_events`, `dwh.silver_events`, and all gold models successfully.
6. `dwh.silver_events` contains only one row per `event_id`.
7. Gold models return non-empty results after data is produced.
8. Adding a new optional JSON field does not stop ingestion.
9. Re-running dbt does not duplicate final gold metrics.
10. README contains working setup and verification steps.

Optional acceptance criteria:

1. `lakehouse.raw_events` is created successfully.
2. The Iceberg batch sink writes data from `dwh.bronze_events`.
3. `meta.batch_job_checkpoint` advances only after successful writes.

## 18. Delivery Rules for the Coding Agent

- Prefer the smallest implementation that satisfies the acceptance criteria.
- Keep all comments and documentation in English.
- Do not introduce components that are not required by this specification.
- Do not change architecture to solve optional features.
- If an optional feature is not completed, document the exact remaining gap and leave the mandatory path working.
- Document assumptions explicitly in `README.md`.

# Implementation Constraints

- Implement the mandatory flow first. Do not start the optional Iceberg path until Redpanda, Doris, and dbt are working end to end.
- Keep the stack limited to Docker Compose, Python, Redpanda, Doris, dbt, and MinIO. Iceberg is the only allowed optional extension.
- Use exact names defined in this specification for topics, tables, models, and files.
- Favor full-refresh-safe table builds for bronze, silver, and gold in phase 1. Do not introduce append-only or complex incremental logic for dbt gold models.
- Keep deduplication only in `dwh.silver_events`. Do not deduplicate in the producer or raw ingestion table.
- Preserve raw debugging context in `ods.raw_ecommerce_events`, including `raw_payload` when practical.
- Treat extra JSON fields as ignorable by default unless explicitly modeled later.
- Keep the local demo deterministic and easy to validate from the README.
- If a Doris or Iceberg feature behaves differently than expected, prefer a documented simplification over adding another runtime component.
- Keep code, SQL, logs, and comments technical and concise.

# Open Questions or Assumptions

- Assumption: `gold_order_cancellation_rate` may use either minute or hour grain; hour grain is acceptable if minute grain is noisy in the local demo.
- Assumption: The optional Iceberg sink may remain as a documented stub in phase 1 if the mandatory pipeline is complete and stable.
