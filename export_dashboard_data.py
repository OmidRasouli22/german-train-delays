"""Save a small copy of the results for the dashboard.

The collected files are far too big for the repo, but the dashboard only
needs the summed up numbers. Those are small enough to commit, which is what
lets the dashboard run on Streamlit Cloud.
"""

import os

import duckdb

DB = "trains.duckdb"
OUT = "dashboard_data"


def main():
    if not os.path.exists(DB):
        print("No %s yet. Run dbt build first." % DB)
        return 1

    os.makedirs(OUT, exist_ok=True)
    con = duckdb.connect(DB, read_only=True)

    # One row per station per day.
    con.sql("select * from agg_station_daily").df().to_parquet(
        os.path.join(OUT, "station_daily.parquet"), index=False)

    # Average delay per hour of day.
    con.sql("""
        select
            hour(planned) as hour,
            count(*) as stops,
            round(avg(delay_minutes), 2) as avg_delay
        from fct_stop_delays
        where delay_minutes is not null
        group by hour
        order by hour
    """).df().to_parquet(os.path.join(OUT, "by_hour.parquet"), index=False)

    # Average delay per kind of train.
    con.sql("""
        select
            train_type,
            count(*) as stops,
            round(avg(delay_minutes), 2) as avg_delay
        from fct_stop_delays
        where delay_minutes is not null
        group by train_type
        having count(*) >= 20
        order by avg_delay desc
    """).df().to_parquet(os.path.join(OUT, "by_train_type.parquet"), index=False)

    # How the delays are spread out.
    con.sql("""
        select
            case
                when delay_minutes < 0 then 'early'
                when delay_minutes = 0 then 'on time'
                when delay_minutes < 6 then '1 to 5 min'
                when delay_minutes < 16 then '6 to 15 min'
                when delay_minutes < 31 then '16 to 30 min'
                else 'over 30 min'
            end as band,
            count(*) as stops,
            min(delay_minutes) as sort_key
        from fct_stop_delays
        where delay_minutes is not null
        group by band
        order by sort_key
    """).df().to_parquet(os.path.join(OUT, "spread.parquet"), index=False)

    for name in sorted(os.listdir(OUT)):
        size = os.path.getsize(os.path.join(OUT, name))
        print("%-26s %5.0f KB" % (name, size / 1024))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
