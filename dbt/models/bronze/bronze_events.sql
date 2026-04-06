select
    event_id,
    lower(event_type) as event_type,
    cast(event_time as datetime) as event_time,
    user_id,
    session_id,
    nullif(order_id, '') as order_id,
    nullif(product_id, '') as product_id,
    cast(quantity as int) as quantity,
    cast(price as decimal(18, 2)) as price,
    upper(currency) as currency,
    lower(status) as status,
    lower(payment_method) as payment_method,
    lower(device) as device,
    lower(source) as source,
    cast(ingested_at as datetime) as ingested_at,
    raw_payload
from {{ source('ods', 'raw_ecommerce_events') }}
