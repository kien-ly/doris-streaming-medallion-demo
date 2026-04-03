CREATE TABLE IF NOT EXISTS ods.raw_ecommerce_events (
    event_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(32) NOT NULL,
    event_time DATETIME NOT NULL,
    user_id VARCHAR(64) NOT NULL,
    session_id VARCHAR(64) NOT NULL,
    order_id VARCHAR(64) NULL,
    product_id VARCHAR(64) NULL,
    quantity INT NULL,
    price DECIMAL(18, 2) NULL,
    currency VARCHAR(8) NULL,
    status VARCHAR(32) NULL,
    payment_method VARCHAR(32) NULL,
    device VARCHAR(32) NULL,
    source VARCHAR(32) NULL,
    ingested_at DATETIME NOT NULL,
    raw_payload STRING NULL
)
DUPLICATE KEY(event_id, event_type, event_time)
DISTRIBUTED BY HASH(event_id) BUCKETS 1
PROPERTIES (
    "replication_num" = "1"
);
