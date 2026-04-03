select
    date_trunc(event_time, 'minute') as metric_minute,
    sum(case when event_type = 'page_view' then 1 else 0 end) as page_view_count,
    sum(case when event_type = 'add_to_cart' then 1 else 0 end) as add_to_cart_count,
    sum(case when event_type = 'checkout_started' then 1 else 0 end) as checkout_started_count,
    sum(case when event_type = 'order_paid' then 1 else 0 end) as order_paid_count
from {{ ref('silver_events') }}
group by 1
