-- A delay of more than a day, or a train arriving hours early, means a time
-- was read wrong rather than a train being very late.
--
-- Real delays get large. Ten hours is possible on a night train. A thousand
-- minutes is not a delay, it is a parsing mistake.

select
    stop_id,
    event,
    station,
    planned,
    actual,
    delay_minutes

from {{ ref('fct_stop_delays') }}

where delay_minutes > 1440
   or delay_minutes < -60
