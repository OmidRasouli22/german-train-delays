# German Rail Punctuality Platform — Design

**Date:** 2026-09-17
**Status:** Approved design, pending implementation plan
**Author:** Omid Rasouli

## Purpose

Build a data platform that continuously captures German rail timetable and delay data,
reconstructs what actually happened for every train at every stop, and serves punctuality
analytics.

The goal is a portfolio project proving data engineering capability: continuous ingestion,
late-arriving data, schema and version changes, reprocessing, and operating a system under
production-like conditions. The learning targets are SQL modelling, dbt, orchestration, and
warehouse design; the collector service builds on existing Python/Node experience.

## Source: DB Timetables API

**Chosen source: Deutsche Bahn Timetables API** (`apis.deutschebahn.com`). Official operator
data, nationwide station coverage including long-distance ICE/IC, free tier.

### Rejected alternatives (probed live on 2026-09-17)

| Source | Coverage | Finding |
|---|---|---|
| gtfs.de realtime | Germany-wide | **Empty.** HTTP 200, valid protobuf, fresh timestamp, **0 entities** across 11+ polls over 40 min. Alternative endpoint names all 404, confirming the URL is right and the feed itself is empty. |
| VBB GTFS-RT | Berlin/Brandenburg | Works (10,094 trip updates/snapshot) but **regional to Berlin**, and publisher states it "has been lacking some data since 2026-06-04". Rejected: wrong geography. |
| MobiData BW | Baden-Württemberg | Live API but **schedules only, no GTFS-RT**. |
| MVV München | Munich | **Static GTFS only**, no realtime feed. |

No free GTFS-RT feed exists for southern Germany. DB's API is the only source giving
Freiburg, Stuttgart and Munich together with long-distance rail.

### Verified API behaviour (measured 2026-09-17)

Authentication uses headers `DB-Client-Id` and `DB-Api-Key`. Note the diagnostic distinction,
which the collector must act on:
- **401 "Invalid client id or secret"** — wrong credentials or wrong header names. Fatal; alert.
- **403 "Not registered to plan"** — valid credentials, missing API subscription. Config error.

Base URL: `https://apis.deutschebahn.com/db-api-marketplace/apis/timetables/v1`

| Endpoint | Purpose | Measured |
|---|---|---|
| `/station/{pattern}` | Resolve station name → EVA number | Stuttgart Hbf `8000096`, München Hbf `8000261`, Freiburg(Breisgau) Hbf `8000107` |
| `/plan/{eva}/{yymmdd}/{hh}` | **Planned** timetable for one station-hour | 10.5 KB, 25 stops (Freiburg, one hour) |
| `/fchg/{eva}` | **All known changes** for a station | 101 KB / 272 records (Freiburg); 296 KB / 578 records (Stuttgart) |
| `/rchg/{eva}` | Recent changes only | Lighter alternative to `/fchg/` |

Rate limit: 60 requests/minute (documented). 25 sequential requests completed in 3.2s with no
throttling, but the collector will respect 60/min regardless — exceeding it risks the key.

Sample delay snapshot (single `/fchg/` call per station):

```
Freiburg Hbf     events=414  with_change=  3  cancellations=33  median +41m
Stuttgart Hbf    events=743  with_change= 67  cancellations=42  median +18m
München Hbf      events=403  with_change= 40  cancellations=25  median +31m
```

### Data model of the source

Times are `yymmddHHMM` strings. Each `<s>` is a stop record with optional `<ar>` (arrival) and
`<dp>` (departure); `pt` = planned time, `ct` = changed/actual time. **Delay = ct − pt.**
Platform: `pp` planned, `cp` changed (128 platform changes observed at Stuttgart).

Nested `<m>` message elements carry operational detail, observed codes:
`c`=cancellation (171), `d`=delay cause (582), `f`=free text (1065), `h`=disruption (166),
`q`=quality change (186). This is **richer than GTFS-RT**, which flattens cancellation reasons away.

**Critical modelling consequence:** `/fchg/` contains only trains *with* changes. It is the
numerator, not the population. True punctuality requires joining `/plan/` (all scheduled trains,
the denominator) to `/fchg/` (the changes). Computing rates from `/fchg/` alone silently measures
"of already-delayed trains, how many are slightly delayed" — a wrong answer that looks plausible.

## Architecture

```
┌──────────────┐  raw XML.gz   ┌─────────────┐   Parquet   ┌──────────┐
│  Collector   │ ────────────> │   Raw zone  │ ──────────> │ DuckDB   │
│ (per-station │  append-only  │ endpoint=/  │   derived   │ warehouse│
│  rotation)   │               │ date=/hour= │             └──────────┘
└──────────────┘               └─────────────┘                   │
       │                                                    dbt models
       │ health metrics                                          │
       v                                                         v
┌──────────────┐                                    ┌────────────────────┐
│ collection_  │                                    │ staging → int →    │
│   health     │                                    │ marts (star schema)│
└──────────────┘                                    └────────────────────┘
                                            ┌──────────────┼───────────┐
                                            v              v           v
                                       Dashboard       FastAPI    Delay model
```

### Components

**1. Collector** — long-running Python service, one container.
Rotates through a configured station list, calling `/fchg/` frequently and `/plan/` hourly.
Responsibilities deliberately minimal: fetch, check whether content changed, write raw gzipped
XML, record a health row. No parsing, no business logic — this component must not crash, so
nothing that changes often lives in it.

Station list is configuration, not code. Initial: Freiburg, Stuttgart, Karlsruhe, Mannheim,
München, Nürnberg and other southern hubs (~20-25 stations).

Must implement: a token-bucket rate limiter (60/min), per-station rotation, and the error
taxonomy above — 401 fatal, 403 config, 5xx retry with backoff, 429 back off hard.

**2. Raw zone** — immutable, partitioned `endpoint=/date=/hour=`.
Never modified. Any parsing bug is fixed by reprocessing from raw. Stored as gzipped XML exactly
as received.

**3. Decoder** — separate batch step, not in the collector.
Parses raw XML into typed Parquet rows. Because it is separate and raw is immutable, it can be
rewritten and re-run over all history.

**4. Warehouse** — DuckDB, dbt models in layers:
- `stg_plan` — planned stop events, flattened and typed
- `stg_changes` — changed/actual stop events
- `stg_messages` — cancellation and disruption messages
- `int_stop_events` — one row per (service_date, train_id, eva, stop_type), plan LEFT JOIN changes
- `fct_stop_delays` — fact table, grain stated explicitly and tested for uniqueness
- `dim_stations` — SCD2, seeded from `/station/`
- `dim_trains` — train/line dimension
- `agg_daily_punctuality` — marts
- `collection_health` — the pipeline's own reliability metrics

**5. Orchestration** — Airflow, added once there is something real to schedule: hourly decode +
dbt run, daily quality checks, compaction.

**6. Serving** — dashboard, FastAPI endpoint, delay-propagation model.

## Key design decisions

**Deduplication vs SCD2 — different problems.**
Picking the final version of a stop event is *deduplication*:
`row_number() over (partition by service_date, train_id, eva, stop_type order by fetched_at desc)`.
SCD2 applies to stations and routes — entities whose attributes change over time and need
`valid_from` / `valid_to`.

**Plan is the denominator.** See the critical consequence above. `int_stop_events` is built as
plan LEFT JOIN changes, never from changes alone.

**HTTP 200 is not data received.**
Demonstrated on day zero: gtfs.de returns successful, valid, fresh, *empty* responses. Health
monitoring counts **records**, not successful requests. A collector measuring request success
would have reported 100% uptime while capturing nothing.

**Cancellations are not delays.** A cancelled train has no delay and must be excluded from delay
averages but counted in reliability. DB's official statistic counts <6 min as punctual and
excludes cancellations; the marts will show both that figure and a cancellation-inclusive one.

**Late-arriving data.** Changes for a train arrive over hours. Incremental models reprocess a
lookback window (2 days) rather than only new rows.

## Known data quality issues (observed in real data)

- Times are `yymmddHHMM` strings with no timezone; German local time with DST transitions.
  A train delayed across the October DST change needs correct handling.
- `/fchg/` returns only changed trains — never treat as the full population.
- Station name search is inexact: "Freiburg" returns "Freiburg Klinikum", not Freiburg Hbf.
  EVA numbers must be resolved once and pinned in config, not looked up by name at runtime.
- Umlauts require explicit UTF-8 handling.
- Trains appear at multiple stations; the same journey is seen from several station feeds and
  must be reconciled by train ID.

## Scope

**In scope:** DB Timetables API ingestion (~20-25 southern German stations), raw archive,
DuckDB warehouse with dbt, Airflow orchestration, punctuality dashboard, health dashboard,
FastAPI, simple delay model.

**Out of scope:** VBB and other GTFS-RT feeds (deferred — the adapter seam stays so a second
source can be added later), Snowflake, weather data (possible later addition), streaming
infrastructure (not justified at this volume).

**Deployment:** laptop first for development. The collector is containerised and portable, so
moving to a VPS later is a `docker compose up` elsewhere. Data captured on a laptop is a
development dataset; the archive that counts starts when it runs on always-on hardware.

## Success criteria

1. Collector runs unattended for days, with gaps detected and visible rather than silent.
2. Raw archive is replayable — decoder can be changed and re-run over all history.
3. `fct_stop_delays` has a stated grain, tested for uniqueness and non-null keys.
4. Punctuality is computed from plan-joined-to-changes, not from changes alone.
5. Health dashboard shows real captured-minutes and real outages.
6. Results reproducible from raw with one command.
