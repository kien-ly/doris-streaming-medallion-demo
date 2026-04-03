CREATE ROUTINE LOAD ods.load_raw_ecommerce_events
ON raw_ecommerce_events
COLUMNS (
    event_id,
    event_type,
    event_time,
    user_id,
    session_id,
    order_id,
    product_id,
    quantity,
    price,
    currency,
    status,
    payment_method,
    device,
    source,
    ingested_at,
    raw_payload
)
PROPERTIES
(
    "desired_concurrent_number" = "1",
    "max_batch_interval" = "10",
    "max_batch_rows" = "200001",
    "max_batch_size" = "104857600",
    "strict_mode" = "false",
    "format" = "json",
    "jsonpaths" = "[\"$.event_id\",\"$.event_type\",\"$.event_time\",\"$.user_id\",\"$.session_id\",\"$.order_id\",\"$.product_id\",\"$.quantity\",\"$.price\",\"$.currency\",\"$.status\",\"$.payment_method\",\"$.device\",\"$.source\",\"$.ingested_at\",\"$.raw_payload\"]",
    "strip_outer_array" = "false",
    "num_as_string" = "false",
    "fuzzy_parse" = "true"
)
FROM KAFKA
(
    "kafka_broker_list" = "redpanda:9092",
    "kafka_topic" = "ecommerce_events",
    "property.group.id" = "doris-ecommerce-events",
    "property.client.id" = "doris-routine-load",
    "property.auto.offset.reset" = "earliest"
);
