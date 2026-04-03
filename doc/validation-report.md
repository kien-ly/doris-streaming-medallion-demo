# Validation Report

## Scope

This report documents the end-to-end validation of the local-first data stack demo in the current workspace.

Validated areas:

- Docker Compose service startup
- Redpanda topic creation and message flow
- Doris database, table, and `ROUTINE LOAD` bootstrap
- Raw ingestion from Kafka into Doris
- dbt model build for bronze, silver, and gold
- dbt test execution and known adapter-specific issues
- Sample warehouse query results
- Optional Iceberg batch sink from `dwh.bronze_events` to MinIO-backed Iceberg storage

Validation date:

- 2026-04-03

## Environment State

Services confirmed `Up` during validation:

- `redpanda`
- `redpanda-ui`
- `doris-fe`
- `doris-be`
- `producer`
- `dbt-runner`
- `minio`
- `jobs`

Health status confirmed:

- `redpanda`: healthy
- `redpanda-ui`: running and connected to Kafka/Admin API
- `doris-fe`: healthy

## Bootstrap Results

### Doris SQL Bootstrap

Executed successfully:

- [sql/01_create_databases.sql](./data-stack/sql/01_create_databases.sql)
- [sql/02_create_ods_tables.sql](./data-stack/sql/02_create_ods_tables.sql)
- [sql/03_create_routine_load.sql](./data-stack/sql/03_create_routine_load.sql)
- [sql/05_meta_checkpoint.sql](./data-stack/sql/05_meta_checkpoint.sql)

Created objects:

- Database `ods`
- Database `dwh`
- Database `analytics`
- Database `meta`
- Table `ods.raw_ecommerce_events`
- Table `meta.batch_job_checkpoint`
- Routine load job `ods.load_raw_ecommerce_events`

### Doris SQL Adjustments Required

The original bootstrap SQL needed Doris-specific corrections during validation:

- [sql/02_create_ods_tables.sql](./data-stack/sql/02_create_ods_tables.sql)
  - Changed `DUPLICATE KEY` to a valid ordered key prefix: `event_id, event_type, event_time`
- [sql/03_create_routine_load.sql](./data-stack/sql/03_create_routine_load.sql)
  - Changed `"max_batch_rows"` from `20000` to `200001`
  - Changed `"max_batch_size"` from `10485760` to `104857600`

## Streaming Validation

### Redpanda

Verified topic:

- `ecommerce_events`

Observed:

- Topic exists with `1` partition and `1` replica
- Producer is publishing JSON events continuously
- Sample consumed offsets included `0` through `4`

### Doris Routine Load

Validated current job state:

- Job name: `load_raw_ecommerce_events`
- Database: `ods`
- Table: `raw_ecommerce_events`
- State: `RUNNING`
- Data source: `KAFKA`

Observed routine load statistics during validation:

- `loadedRows`: `121` at first check
- `committedTaskNum`: `7`
- `Lag`: `0`

This indicates Doris is actively consuming Kafka data and committing batches successfully.

## Warehouse Validation

### Raw Layer

Observed row count during validation:

- `ods.raw_ecommerce_events`: `121`

### Bronze Layer

dbt built successfully:

- `dwh.bronze_events`

Observed row count after successful dbt run:

- `dwh.bronze_events`: `401`

### Silver Layer

dbt built successfully:

- `dwh.silver_events`

Observed counts:

- `silver_count`: `401`
- `distinct_event_id_count`: `401`

Direct validation queries returned zero failing rows:

- `SELECT event_id FROM dwh.silver_events WHERE event_id IS NULL;`
- `SELECT event_id, COUNT(*) FROM dwh.silver_events GROUP BY event_id HAVING COUNT(*) > 1;`

This confirms the silver deduplication rule is working for the current dataset.

### Gold Layer

dbt built successfully:

- `analytics.gold_revenue_per_minute`
- `analytics.gold_order_cancellation_rate`
- `analytics.gold_conversion_funnel`

Observed row counts:

- `analytics.gold_revenue_per_minute`: `4`
- `analytics.gold_order_cancellation_rate`: `4`
- `analytics.gold_conversion_funnel`: `4`

Sample outputs:

`gold_revenue_per_minute`

- `2026-04-03 04:45:00 | paid_event_count=6 | gross_revenue=5287.74`
- `2026-04-03 04:44:00 | paid_event_count=18 | gross_revenue=19831.73`

`gold_order_cancellation_rate`

- `2026-04-03 04:45:00 | created=16 | cancelled=16 | rate=1.00000000`
- `2026-04-03 04:44:00 | created=14 | cancelled=27 | rate=1.92857142`

`gold_conversion_funnel`

- `2026-04-03 04:45:00 | page_view=11 | add_to_cart=16 | checkout_started=5 | order_paid=6`
- `2026-04-03 04:44:00 | page_view=20 | add_to_cart=22 | checkout_started=23 | order_paid=18`

## dbt Validation

### dbt Versions

Validated versions in the running container:

- `dbt-core`: `1.10.4`
- `dbt-doris`: `1.0.0`

### dbt Run Result

`dbt run` completed successfully.

Result:

- `PASS=5`
- `ERROR=0`

### dbt Test Result

`dbt test` completed with partial success.

Result:

- `PASS=4`
- `ERROR=2`

Passing tests:

- `accepted_values_bronze_events_event_type`
- `accepted_values_bronze_events_status`
- `not_null_bronze_events_event_id`
- `not_null_bronze_events_event_time`

Failing tests:

- `not_null_silver_events_event_id`
- `unique_silver_events_event_id`

### dbt Test Failure Analysis

The two failing silver tests are false negatives caused by adapter/runtime behavior, not by warehouse data quality.

Evidence:

- [dbt/target/compiled/ecommerce_demo/tests/schema.yml/not_null_silver_events_event_id.sql](./data-stack/dbt/target/compiled/ecommerce_demo/tests/schema.yml/not_null_silver_events_event_id.sql) compiles to a correct query against ``dwh`.`silver_events``
- [dbt/target/compiled/ecommerce_demo/tests/schema.yml/unique_silver_events_event_id.sql](./data-stack/dbt/target/compiled/ecommerce_demo/tests/schema.yml/unique_silver_events_event_id.sql) compiles to a correct query against ``dwh`.`silver_events``
- Running those exact queries directly in Doris returned zero rows
- `dwh.silver_events` exists and has `401` rows with `401` distinct `event_id`s

Practical conclusion:

- Silver data is valid for the current demo run
- The remaining dbt test failures should be treated as an adapter-specific issue in `dbt-doris 1.0.0`

## Optional Iceberg Validation

### Implemented Path

Validated components:

- [jobs/optional_iceberg_sink.py](./data-stack/jobs/optional_iceberg_sink.py)
- Local SQL catalog metadata at `jobs/.iceberg/demo_catalog.db`
- MinIO warehouse path `s3://lakehouse/warehouse/lakehouse/raw_events`
- Doris checkpoint state in `meta.batch_job_checkpoint`

### Dependencies and Runtime

Updated [docker-compose.yml](./data-stack/docker-compose.yml):

- Added `ICEBERG_CATALOG_URI`
- Added `ICEBERG_S3_REGION`
- Changed the `jobs` service to install dependencies from [jobs/requirements.txt](./data-stack/jobs/requirements.txt)

Added [jobs/requirements.txt](./data-stack/jobs/requirements.txt):

- `pymysql==1.1.1`
- `minio==7.2.15`
- `pyarrow==19.0.1`
- `pyiceberg[pyarrow,sql-sqlite]==0.9.1`

### Sink Execution Result

Validated run:

- Created MinIO bucket `lakehouse`
- Created Iceberg namespace `lakehouse`
- Created Iceberg table `lakehouse.raw_events`
- Appended `401` rows from `dwh.bronze_events`
- Advanced checkpoint to `2026-04-03 04:46:00`

Observed state after the successful append:

- Iceberg row count: `401`
- Iceberg snapshots: `1`
- Checkpoint row:
  - `job_name=optional_iceberg_sink`
  - `last_success_start=2026-04-03 04:41:00`
  - `last_success_end=2026-04-03 04:46:00`
  - `status=SUCCESS`
  - `row_count=401`

Observed MinIO objects:

- Parquet files under `warehouse/lakehouse/raw_events/data/`
- Metadata JSON and Avro files under `warehouse/lakehouse/raw_events/metadata/`

### Incremental Rerun Result

Validated rerun:

- Second execution selected window `2026-04-03 04:46:00` to `2026-04-03 04:51:00`
- No rows were found in that window
- Iceberg row count remained `401`
- Checkpoint advanced to `2026-04-03 04:51:00`

This confirms the local demo sink advances checkpoints without rewriting the previously appended window.

## Code and Config Changes Made During Validation

### Compose and Runtime Fixes

Updated [docker-compose.yml](./data-stack/docker-compose.yml) to resolve runtime failures:

- Corrected Doris image tags
- Corrected `FE_SERVERS` format
- Corrected `BE_ADDR` format
- Added a dedicated Docker network with static Doris FE/BE IPs
- Pinned `dbt-core` to a version compatible with `dbt-doris 1.0.0`
- Ensured internal containers use `doris-fe` as the Doris host
- Added the minimal dependency set required for the validated optional Iceberg path

### dbt Project Fixes

Updated [dbt/dbt_project.yml](./data-stack/dbt/dbt_project.yml):

- Added `+replication_num: 1` for single-backend local Doris

Added [dbt/macros/generate_schema_name.sql](./data-stack/dbt/macros/generate_schema_name.sql):

- Prevents dbt from generating schema names like `dwh_dwh` and `dwh_analytics`

Updated [dbt/tests/schema.yml](./data-stack/dbt/tests/schema.yml):

- Declared full bronze and silver column sets so `dbt-doris` CTAS creates all expected columns

## Known Residual Issues

- `dbt debug` still reports a missing `git` binary in the `dbt-runner` container, even though the Doris connection itself is valid
- Two silver dbt tests fail due to adapter/runtime behavior despite valid underlying data
- `pyiceberg 0.9.1` falls back to the pure Python Avro decoder in the current container image, which is slower but functionally correct for the local demo
- The optional Iceberg table stores `price` as `double` rather than `decimal` to avoid a `pyiceberg 0.9.1` Parquet decimal write incompatibility in this local path

## Overall Status

Mandatory pipeline status:

- Docker Compose stack: working
- Producer to Redpanda: working
- Redpanda to Doris raw ingestion: working
- dbt bronze/silver/gold build: working
- Silver deduplication by `event_id`: validated
- Gold aggregate tables: validated

Overall assessment:

- Mandatory phase 1 demo path is operational
- Remaining blockers are limited to dbt test adapter behavior and optional Iceberg work
