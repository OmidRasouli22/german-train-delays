-- The latest known state of each stop.
--
-- The same train is fetched again every two minutes, so the raw events hold
-- many versions of the same stop. Only the newest one is true.

with ranked as (

    select
        stop_id,
        event,
        actual,
        actual_platform,
        cancelled,
        fetched,
        row_number() over (
            partition by stop_id, event
            order by fetched desc
        ) as newest

    from {{ source('rail', 'fchg') }}

)

select
    stop_id,
    event,
    actual,
    actual_platform,
    cancelled

from ranked
where newest = 1
