-- One row per station per day.
--
-- This is what a dashboard reads. Counting from the stops table every time a
-- chart loads is wasteful


select
    service_date,
    station,
    eva,

    count(*) as scheduled,
    count(*) filter (where not cancelled) as ran,
    count(*) filter (where cancelled) as cancelled,

    count(*) filter (where delay_minutes < 6) as on_time,
    count(*) filter (where delay_minutes >= 6) as late,
    count(*) filter (where delay_minutes >= 16) as very_late,

    round(avg(delay_minutes), 1) as avg_delay,
    max(delay_minutes) as worst_delay,

    round(
        100.0 * count(*) filter (where delay_minutes < 6)
        / nullif(count(*) filter (where not cancelled), 0)
    , 1) as punctuality,

    round(
        100.0 * count(*) filter (where delay_minutes < 6)
        / nullif(count(*), 0)
    , 1) as punctuality_with_cancellations

from {{ ref('fct_stop_delays') }}

group by service_date, station, eva
