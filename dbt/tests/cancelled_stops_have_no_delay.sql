-- A cancelled train was never late, because it never ran. It must have no
-- delay at all.
--
-- Note that a cancelled stop can still carry an arrival time. The API keeps
-- the last prediction it made before the cancellation, so about six in ten
-- cancelled stops still show a time. That is upstream behaviour, not a
-- mistake here, which is why this checks the delay instead.

select
    stop_id,
    event,
    station,
    delay_minutes

from {{ ref('fct_stop_delays') }}

where cancelled
  and delay_minutes is not null
