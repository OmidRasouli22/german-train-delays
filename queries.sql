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


-- Do long distance trains run later than local ones?
-- Types with fewer than 20 stops are left out, because a handful of trains
-- is not enough to say anything.
select
    train_type,
    count(*) as stops,
    round(avg(delay_minutes), 1) as avg_delay,
    max(delay_minutes) as worst
from 'stops.parquet'
where delay_minutes is not null
group by train_type
having count(*) >= 20
order by avg_delay desc;


-- Are trains later at busy times of day?
-- The hour is German local time, so 08:00 is the morning rush as a
-- passenger would know it.
select
    hour(planned) as hour_of_day,
    count(*) as stops,
    round(avg(delay_minutes), 1) as avg_delay
from 'stops.parquet'
where delay_minutes is not null
group by hour_of_day
having count(*) >= 20
order by hour_of_day;
