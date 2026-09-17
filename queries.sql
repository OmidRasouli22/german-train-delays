-- Questions to ask the collected data.
--
-- Run them all with:
--   python ask.py
-- or copy one into a DuckDB shell.
--
-- Cancelled trains have no delay, so most queries skip them. They are not
-- late, they never ran. Counting them as on time would flatter the numbers.


-- Which station has the worst delays?
select
    station,
    count(*) as stops,
    round(avg(delay_minutes), 1) as avg_delay,
    max(delay_minutes) as worst
from 'stops.parquet'
where delay_minutes is not null
group by station
order by avg_delay desc;


-- Long distance trains against local ones.
-- ICE and IC cross the country, so they have more time to fall behind.
select
    train_type,
    count(*) as stops,
    round(avg(delay_minutes), 1) as avg_delay
from 'stops.parquet'
where delay_minutes is not null
group by train_type
having count(*) >= 10
order by avg_delay desc;


-- Does the time of day matter?
select
    hour(planned) as hour_of_day,
    count(*) as stops,
    round(avg(delay_minutes), 1) as avg_delay
from 'stops.parquet'
where delay_minutes is not null
group by hour_of_day
order by hour_of_day;


-- The official measure counts a train as on time under six minutes.
-- Cancelled trains are left out of it, which is the usual criticism.
-- This shows both, so the difference is visible.
select
    station,
    count(*) as all_stops,
    round(100.0 * count(*) filter (where delay_minutes < 6)
          / nullif(count(*) filter (where not cancelled), 0), 1) as on_time_official,
    round(100.0 * count(*) filter (where delay_minutes < 6)
          / count(*), 1) as on_time_with_cancellations
from 'stops.parquet'
group by station
order by on_time_official;


-- Most delay is small. A few trains are very late and drag the average up,
-- so the spread says more than the mean.
select
    case
        when delay_minutes < 0 then 'early'
        when delay_minutes = 0 then 'on time'
        when delay_minutes < 6 then '1 to 5 min'
        when delay_minutes < 16 then '6 to 15 min'
        when delay_minutes < 31 then '16 to 30 min'
        else 'over 30 min'
    end as delay_band,
    count(*) as stops
from 'stops.parquet'
where delay_minutes is not null
group by delay_band
order by min(delay_minutes);


-- Arriving late and leaving late are different things. A train can arrive
-- late and make some of it back while standing at the platform.
select
    event,
    count(*) as stops,
    round(avg(delay_minutes), 1) as avg_delay
from 'stops.parquet'
where delay_minutes is not null
group by event;


-- Which individual trains were worst?
select
    train_type,
    train_number,
    station,
    event,
    planned,
    delay_minutes
from 'stops.parquet'
where delay_minutes is not null
order by delay_minutes desc
limit 10;
