with ranked as (
    select
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
        raw_payload,
        row_number() over (
            partition by event_id
            order by ingested_at desc, event_time desc
        ) as row_num
    from {{ ref('bronze_events') }}
    where event_id is not null
      and event_time is not null
)
select
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
from ranked
where row_num = 1

