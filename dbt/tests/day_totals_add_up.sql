-- Every stop is either on time, late, or cancelled. If the three do not add
-- up to the number scheduled, something has been counted twice or lost.

select
    service_date,
    station,
    scheduled,
    on_time + late + cancelled as counted

from {{ ref('agg_station_daily') }}

where scheduled != on_time + late + cancelled
