with created_orders as (
    select
        date_trunc(event_time, 'minute') as metric_minute,
        count(*) as created_delta,
        0 as cancelled_delta
    from {{ ref('silver_events') }}
    where event_type = 'order_created'
    group by 1
),
cancelled_orders as (
    select
        date_trunc(event_time, 'minute') as metric_minute,
        0 as created_delta,
        count(*) as cancelled_delta
    from {{ ref('silver_events') }}
    where event_type = 'order_cancelled'
    group by 1
),
unioned as (
    select * from created_orders
    union all
    select * from cancelled_orders
)
select
    metric_minute,
    sum(created_delta) as created_order_count,
    sum(cancelled_delta) as cancelled_order_count,
    case
        when sum(created_delta) = 0 then 0
        else cast(sum(cancelled_delta) as decimal(18, 4)) / sum(created_delta)
    end as cancellation_rate
from unioned
group by metric_minute
