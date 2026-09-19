-- The timetable. What time each train was supposed to arrive or leave.
--
-- The plan is fetched once an hour, so the same stop appears in several
-- files. Only the newest copy is kept, the same way as for the changes.
--
-- This side also carries the train type and number, which the changes
-- usually leave out.

with ranked as (

    select
        stop_id,
        event,
        eva,
        station,
        planned,
        line,
        planned_platform,
        train_type,
        train_number,
        row_number() over (
            partition by stop_id, event
            order by fetched desc
        ) as newest

    from {{ source('rail', 'plan') }}

)

select
    stop_id,
    event,
    eva,
    station,
    planned,
    line,
    planned_platform,
    train_type,
    train_number

from ranked
where newest = 1
