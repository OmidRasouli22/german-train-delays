# German Transit Punctuality Platform — Design

**Date:** 2026-09-17
**Status:** Approved design, pending implementation plan
**Author:** Omid Rasouli

## Purpose

Build a data platform that continuously captures GTFS-Realtime transit data, reconstructs what
actually happened for every trip at every stop, and serves punctuality analytics.

The goal is a portfolio project proving data engineering capability: continuous ingestion,
late-arriving data, schema and version changes, reprocessing, and operating a system under
production-like conditions. The learning targets are SQL modelling, dbt, orchestration, and
warehouse design; the collector builds on existing Python/Node service experience.

## Source investigation (measured 2026-09-17)

Endpoints were probed directly rather than trusted from documentation. Findings:

| Source | Result | Notes |
|---|---|---|
| `realtime.gtfs.de/realtime-free.pb` | **Empty** | HTTP 200, valid protobuf, fresh timestamp, **0 entities** across 11 polls over ~5 min |
| `production.gtfsrt.vbb.de/data` | **Live** | 10.68 MB, 10,094 trip updates, 211,364 stop-time updates |
| gtfs.de static `fv_free` | 0.41 MB | Long-distance rail; last modified 2026-09-12 (5 days stale, not daily) |
| gtfs.de static `rv_free` | 11.2 MB | Regional rail |
| gtfs.de static `nv_free` | 273 MB | Local transport — 96% of total volume |

The gtfs.de realtime feed is the documented primary source and is currently serving a
well-formed but entirely empty feed. Alternative endpoint names (`realtime-fv.pb`,
`realtime-rv.pb`, `realtime.pb`) all return 404, confirming the URL is correct and the feed
itself is empty rather than moved. VBB publishes its own feed which works, with a stated caveat
that it "has been lacking some data since 2026-06-04".

**Consequence:** the platform is designed multi-source from the start. Upstream unreliability is
a requirement, not an edge case.

### Storage measurement

Two VBB snapshots 60 seconds apart were compared at the stop-time-update grain:

```
rows:     211,746 -> 211,765
new 1,257 | gone 1,238 | common 210,508 | changed 1,083
changed-only rows: 2,340 = 1.1% of snapshot
```

| Strategy | Per day | Per 90 days |
|---|---|---|
| Full snapshots, gzipped | 3.41 GB | **307 GB** |
| Changed rows only | 0.038 GB | **3.4 GB** |

A 90x reduction. Full-snapshot storage is not viable on a laptop; change-only storage is.

## Architecture

```
┌──────────────┐   raw .pb.gz    ┌─────────────┐   Parquet   ┌──────────┐
│  Collector   │ ──────────────> │   Raw zone  │ ──────────> │ DuckDB   │
│ (multi-feed) │   append-only   │ date=/hour= │   derived   │ warehouse│
└──────────────┘                 └─────────────┘             └──────────┘
       │                                                           │
       │ health metrics                                       dbt models
       v                                                           │
┌──────────────┐                                                   v
│ collection_  │                                         ┌────────────────────┐
│   health     │                                         │ staging → int →    │
└──────────────┘                                         │ marts (star schema)│
                                                         └────────────────────┘
                                                                   │
                                            ┌──────────────────────┼───────────┐
                                            v                      v           v
                                       Dashboard              FastAPI     Delay model
```

### Components

**1. Collector** — long-running Python service, one container.
Polls a *list* of feeds on independent schedules. Responsibilities are deliberately minimal:
fetch bytes, check whether the header timestamp advanced, write raw gzipped protobuf, record a
health row. No parsing, no filtering, no business logic — this is the component that must not
crash, so nothing that changes often lives here.

Feed list is configuration, not code. Initial entries: VBB (live), gtfs.de (currently empty,
polled anyway so recovery is captured automatically).

**2. Raw zone** — immutable, partitioned `feed=/date=/hour=`.
Never modified. Any parsing bug is fixed by reprocessing from raw. Written as gzipped protobuf
exactly as received, preserving fidelity for replay.

**3. Decoder** — separate batch step, not in the collector.
Reads raw protobuf, emits changed rows only as Parquet, partitioned by date. Because it is
separate and raw is immutable, it can be rewritten and re-run over history at any time.

**4. Warehouse** — DuckDB, dbt models in layers:
- `stg_trip_updates` — flattened, typed, cleaned
- `stg_static_*` — timetable from versioned static feeds
- `int_stop_events` — one row per (service_date, trip_id, stop_sequence), planned joined to latest actual
- `fct_stop_delays` — fact table, grain stated explicitly and tested for uniqueness
- `dim_stations`, `dim_routes` — SCD2 dimensions
- `dim_feed_versions` — static feed versioning, SCD2
- `agg_daily_punctuality` — marts
- `collection_health` — pipeline's own reliability metrics

**5. Orchestration** — Airflow, added only once there is something real to schedule:
daily static feed download, hourly decode + dbt run, data quality checks, compaction.

**6. Serving** — dashboard, FastAPI endpoint, delay-propagation model.

## Key design decisions

**Deduplication vs SCD2 — these are different problems.**
Picking the final version of a stop event is *deduplication*:
`row_number() over (partition by service_date, trip_id, stop_sequence order by feed_timestamp desc)`.
SCD2 applies to stations, routes, and static feed versions — entities whose attributes change
over time and need `valid_from` / `valid_to`.

**Static feed versioning is mandatory.**
Static feeds have limited validity and trip IDs change between versions. Joining realtime data to
the wrong timetable version produces silently wrong results. Each static download is stored as a
distinct version; realtime rows join to the version valid on their service date.

**HTTP 200 is not data received.**
Demonstrated on day zero: gtfs.de returns a successful, valid, fresh, *empty* response. Health
monitoring counts **entities**, not successful requests. A collector measuring request success
would have reported 100% uptime while capturing nothing.

**Change-only storage, with raw preserved.**
Raw protobuf is the archive; Parquet holds changed rows. Fidelity is kept without the 307 GB.

**Late-arriving data.**
Updates for a trip arrive over hours. Incremental models reprocess a lookback window (2 days)
rather than only new rows.

## Known data quality issues (observed in real data)

- `stop_id` format is inconsistent *within a single trip*: bare numeric (`900203812`) alongside
  DELFI-style (`de:12065:900203812::1`). Requires normalisation before joining to the timetable.
- The first `stop_time_update` of a trip may omit `stop_sequence`.
- Cancellations present as `schedule_relationship: CANCELED` (63 in one snapshot) and must be
  handled separately from delays — a cancelled train has no delay, and excluding cancellations
  inflates punctuality.
- VBB feed is documented as incomplete since 2026-06-04.

## Scope

**In scope:** VBB + gtfs.de realtime, static timetable versioning, DuckDB warehouse with dbt,
Airflow orchestration, punctuality dashboard, health dashboard, FastAPI, simple delay model.

**Out of scope:** Germany-wide long-distance coverage (VBB is Berlin/Brandenburg regional — the
project must be labelled accurately), DB Timetables API, Snowflake, weather data (possible later
addition), streaming infrastructure (Kafka etc. — not justified at this volume).

**Deployment:** laptop first for development. The collector is containerised and portable, so
moving to a VPS later is a `docker compose up` elsewhere. Data captured on a laptop is a
development dataset; the archive that counts starts when it runs on always-on hardware.

## Success criteria

1. Collector runs unattended for days, with gaps detected and visible rather than silent.
2. Raw archive is replayable — decoder can be changed and re-run over all history.
3. `fct_stop_delays` has a stated grain, tested for uniqueness and non-null keys.
4. Static feed version changes do not silently corrupt joins.
5. Health dashboard shows real captured-minutes and real outages, including the gtfs.de outage.
6. Punctuality results reproducible from raw with one command.
