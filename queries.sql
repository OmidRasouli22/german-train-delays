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


-- What actually happened at each station?
-- A stop ends one of three ways: on time, late, or cancelled. A cancelled
-- The official measure counts a train as on time under six minutes late and
-- leaves cancelled trains out altogether. That is the number DB publishes.
select
    station,
    count(*) as scheduled,
    count(*) filter (where delay_minutes < 6) as on_time,
    count(*) filter (where delay_minutes >= 6) as late,
    count(*) filter (where cancelled) as cancelled,
    round(100.0 * count(*) filter (where delay_minutes < 6)
          / nullif(count(*) filter (where not cancelled), 0), 1) as official,
    round(100.0 * count(*) filter (where delay_minutes < 6)
          / count(*), 1) as share_of_all
from 'stops.parquet'
group by station
order by official desc;


-- How are the delays spread out?
-- An average hides the shape. Most trains are close to on time and a few are
-- very late, so the bands say more than the mean does.
select
    case
        when delay_minutes < 0 then 'early'
        when delay_minutes = 0 then 'exactly on time'
        when delay_minutes < 6 then '1 to 5 min'
        when delay_minutes < 16 then '6 to 15 min'
        when delay_minutes < 31 then '16 to 30 min'
        else 'over 30 min'
    end as band,
    count(*) as stops,
    round(100.0 * count(*) / sum(count(*)) over (), 1) as percent
from 'stops.parquet'
where delay_minutes is not null
group by band
order by min(delay_minutes);


-- Do trains make up time while standing at a platform?
-- Comparing all arrivals against all departures does not answer this, because
-- they are different trains. A train starting its journey here departs on
-- time and has no delay to recover, which flatters the departure average.
-- So this pairs the arrival and the departure of the same train instead.
with paired as (
    select
        stop_id,
        max(delay_minutes) filter (where event = 'arrival') as arrived,
        max(delay_minutes) filter (where event = 'departure') as departed
    from 'stops.parquet'
    where delay_minutes is not null
    group by stop_id
)
select
    count(*) as trains,
    round(avg(arrived), 1) as avg_arrival,
    round(avg(departed), 1) as avg_departure,
    round(avg(departed - arrived), 1) as avg_change,
    count(*) filter (where departed < arrived) as made_up_time,
    count(*) filter (where departed > arrived) as lost_more
from paired
where arrived is not null and departed is not null;


-- Which single stops were worst?
-- Worth looking at now and then. A delay of several hours is usually a real
-- train, but it can also be a sign that something was parsed wrong.
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
