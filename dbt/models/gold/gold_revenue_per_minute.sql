select
    date_trunc(event_time, 'minute') as metric_minute,
    count(*) as paid_event_count,
    sum(coalesce(price, 0) * coalesce(quantity, 1)) as gross_revenue
from {{ ref('silver_events') }}
where event_type = 'order_paid'
group by 1
