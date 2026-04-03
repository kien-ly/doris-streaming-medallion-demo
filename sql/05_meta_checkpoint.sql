CREATE TABLE IF NOT EXISTS meta.batch_job_checkpoint (
    job_name VARCHAR(128) NOT NULL,
    source_table VARCHAR(256) NOT NULL,
    target_table VARCHAR(256) NOT NULL,
    last_success_start DATETIME NULL,
    last_success_end DATETIME NULL,
    status VARCHAR(32) NOT NULL,
    row_count BIGINT NULL,
    updated_at DATETIME NOT NULL
)
UNIQUE KEY(job_name, source_table, target_table)
DISTRIBUTED BY HASH(job_name) BUCKETS 1
PROPERTIES (
    "replication_num" = "1"
);

