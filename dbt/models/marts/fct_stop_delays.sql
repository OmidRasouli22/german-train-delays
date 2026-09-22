-- One row per train, per station, per arrival or departure.
--
-- Built one day at a time instead of all at once. A train keeps being
-- updated for hours after it was due, so the last two days are always
-- rebuilt rather than only the new rows. Anything older than that has
-- stopped changing.

{{
    config(
        materialized='incremental',
        unique_key=['stop_id', 'event'],
        incremental_strategy='delete+insert'
    )
}}

with plan as (

    select * from {{ ref('stg_plan') }}

    {% if is_incremental() %}
    where planned >= current_date - interval 2 day
    {% endif %}

),

changes as (
    select * from {{ ref('stg_changes') }}
),

joined as (

    select
        plan.stop_id,
        plan.event,
        plan.eva,
        plan.station,
        plan.planned,
        plan.line,
        plan.train_type,
        plan.train_number,
        plan.planned_platform,
        changes.actual,
        changes.actual_platform,
        coalesce(changes.cancelled, false) as cancelled

    from plan
    left join changes
        on plan.stop_id = changes.stop_id
        and plan.event = changes.event

)

select
    stop_id,
    event,
    eva,
    station,
    planned,
    actual,
    line,
    train_type,
    train_number,
    planned_platform,
    actual_platform,
    cancelled,

    -- A day of service runs past midnight, so anything before 03:00 belongs
    -- to the evening before. Without this the night trains split in two.
    case
        when hour(planned) < 3 then date(planned - interval 1 day)
        else date(planned)
    end as service_date,

    -- How late, in minutes. No change seen means the train was on time.
    -- A cancelled train gets nothing, because it never ran and so was
    -- never late.
    case
        when cancelled then null
        when actual is null then 0
        else datediff('minute', planned, actual)
    end as delay_minutes

from joined
