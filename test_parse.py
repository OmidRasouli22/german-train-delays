"""Tests for the parsing and delay logic."""

import gzip
from datetime import date, datetime

import pandas as pd

from parse import (GERMAN_TIME, build_stops, eva_from_path, file_time,
                   latest_only, read_file, read_time, service_date)


def test_read_time():
    assert read_time("2609171605") == datetime(2026, 9, 17, 16, 5, tzinfo=GERMAN_TIME)


def test_read_time_empty():
    assert read_time(None) is None
    assert read_time("") is None


def test_file_time(tmp_path):
    day = tmp_path / "2026-09-17"
    day.mkdir()
    path = day / "8000096_115833.xml.gz"
    assert file_time(str(path)) == datetime(2026, 9, 17, 11, 58, 33)


def test_eva_from_path():
    assert eva_from_path("data/fchg/2026-09-17/8000096_115833.xml.gz") == "8000096"


def write_xml(tmp_path, text):
    """Save some XML the way the collector does, so we can read it back."""
    day = tmp_path / "2026-09-17"
    day.mkdir(exist_ok=True)
    path = day / "8000107_120000.xml.gz"
    with gzip.open(path, "wb") as f:
        f.write(text.encode("utf-8"))
    return str(path)


def test_read_file_arrival_and_departure(tmp_path):
    path = write_xml(tmp_path, """
        <timetable station="Freiburg Hbf" eva="8000107">
          <s id="trip1">
            <ar pt="2609171605" ct="2609171636" pp="3"/>
            <dp pt="2609171610" ct="2609171640" pp="3"/>
          </s>
        </timetable>
    """.strip())

    rows = read_file(path)

    assert len(rows) == 2
    assert rows[0]["event"] == "arrival"
    assert rows[1]["event"] == "departure"
    assert rows[0]["planned"] == datetime(2026, 9, 17, 16, 5, tzinfo=GERMAN_TIME)
    assert rows[0]["actual"] == datetime(2026, 9, 17, 16, 36, tzinfo=GERMAN_TIME)


def test_read_file_marks_cancelled(tmp_path):
    """A cancelled stop is marked with cs="c" on the arrival or departure."""
    path = write_xml(tmp_path, """
        <timetable station="Freiburg Hbf" eva="8000107">
          <s id="trip1">
            <ar pt="2609171605" cs="c" clt="2609171610"/>
          </s>
        </timetable>
    """.strip())

    rows = read_file(path)

    assert rows[0]["cancelled"] is True


def test_disruption_message_is_not_a_cancellation(tmp_path):
    """An <m> message means a disruption. The train still ran."""
    path = write_xml(tmp_path, """
        <timetable station="Freiburg Hbf" eva="8000107">
          <s id="trip1">
            <m id="m1" t="c"/>
            <ar pt="2609171605" ct="2609171630"/>
          </s>
        </timetable>
    """.strip())

    rows = read_file(path)

    assert rows[0]["cancelled"] is False


def test_read_file_keeps_umlauts(tmp_path):
    path = write_xml(tmp_path, """
        <timetable station="München Hbf" eva="8000261">
          <s id="trip1"><ar pt="2609171605"/></s>
        </timetable>
    """.strip())

    rows = read_file(path)

    assert rows[0]["station"] == "München Hbf"


def test_read_file_ignores_broken_xml(tmp_path):
    path = write_xml(tmp_path, "<timetable><s id=")

    assert read_file(path) == []


def test_latest_only_keeps_newest():
    """The same stop is fetched again every two minutes. Keep the last one."""
    table = pd.DataFrame([
        {"stop_id": "trip1", "event": "arrival", "actual": "16:30",
         "fetched": datetime(2026, 9, 17, 12, 0)},
        {"stop_id": "trip1", "event": "arrival", "actual": "16:36",
         "fetched": datetime(2026, 9, 17, 12, 2)},
    ])

    result = latest_only(table, ["stop_id", "event"])

    assert len(result) == 1
    assert result.iloc[0]["actual"] == "16:36"


def make_plan(**changes):
    row = {
        "stop_id": "trip1", "event": "arrival", "eva": "8000107",
        "station": "Freiburg Hbf", "planned": datetime(2026, 9, 17, 16, 5),
        "line": "ICE", "planned_platform": "3", "train_type": "ICE",
        "train_number": "107", "fetched": datetime(2026, 9, 17, 12, 0),
    }
    row.update(changes)
    return pd.DataFrame([row])


def make_changes(**changes):
    row = {
        "stop_id": "trip1", "event": "arrival",
        "actual": datetime(2026, 9, 17, 16, 36),
        "actual_platform": "5", "cancelled": False,
        "fetched": datetime(2026, 9, 17, 12, 2),
    }
    row.update(changes)
    return pd.DataFrame([row])


def test_delay_is_actual_minus_planned():
    stops = build_stops(make_plan(), make_changes())

    assert stops.iloc[0]["delay_minutes"] == 31


def test_early_train_gets_negative_delay():
    changes = make_changes(actual=datetime(2026, 9, 17, 16, 2))

    stops = build_stops(make_plan(), changes)

    assert stops.iloc[0]["delay_minutes"] == -3


def test_stop_with_no_change_is_on_time():
    """Most trains never appear in the changes. They ran as planned."""
    empty = make_changes().iloc[0:0]

    stops = build_stops(make_plan(), empty)

    assert len(stops) == 1
    assert stops.iloc[0]["delay_minutes"] == 0
    assert not stops.iloc[0]["cancelled"]


def test_cancelled_train_has_no_delay():
    """A cancelled train is not late. Counting it as late would be wrong."""
    changes = make_changes(cancelled=True)

    stops = build_stops(make_plan(), changes)

    assert stops.iloc[0]["cancelled"]
    assert pd.isna(stops.iloc[0]["delay_minutes"])


def test_every_planned_stop_is_kept():
    """The plan is the full list of trains. Nothing may be dropped."""
    plan = pd.concat([make_plan(stop_id="a"), make_plan(stop_id="b")])
    changes = make_changes(stop_id="a")

    stops = build_stops(plan, changes)

    assert sorted(stops["stop_id"]) == ["a", "b"]


def test_one_row_per_stop_and_event():
    """The table must not gain rows from the join."""
    plan = pd.concat([
        make_plan(stop_id="a", event="arrival"),
        make_plan(stop_id="a", event="departure"),
    ])
    changes = pd.concat([
        make_changes(stop_id="a", event="arrival"),
        make_changes(stop_id="a", event="departure"),
    ])

    stops = build_stops(plan, changes)

    assert len(stops) == 2
    assert not stops.duplicated(subset=["stop_id", "event"]).any()


def test_delay_across_midnight():
    """A train planned at 23:55 arriving 00:10 is 15 minutes late, not late by a day."""
    plan = make_plan(planned=datetime(2026, 9, 17, 23, 55))
    changes = make_changes(actual=datetime(2026, 9, 18, 0, 10))

    stops = build_stops(plan, changes)

    assert stops.iloc[0]["delay_minutes"] == 15


def test_times_are_german_not_utc():
    """The API sends German local time. It must stay German."""
    t = read_time("2609180900")

    assert t.hour == 9
    assert t.utcoffset().total_seconds() == 2 * 3600  # summer time


def test_winter_time_offset_changes():
    """After the October change the offset is one hour, not two."""
    summer = read_time("2609180900")
    winter = read_time("2611010900")

    assert summer.utcoffset().total_seconds() == 2 * 3600
    assert winter.utcoffset().total_seconds() == 1 * 3600
    assert summer.hour == winter.hour == 9


def test_delay_is_not_broken_by_the_clock_change():
    """A train running through the October change is not an hour late."""
    plan = make_plan(planned=read_time("2610250145"))
    changes = make_changes(actual=read_time("2610250150"))

    stops = build_stops(plan, changes)

    assert stops.iloc[0]["delay_minutes"] == 5


def test_service_date_of_an_evening_train():
    assert service_date(read_time("2609172230")) == date(2026, 9, 17)


def test_after_midnight_belongs_to_the_day_before():
    """A train at 00:30 is part of the evening it started in."""
    assert service_date(read_time("2609180030")) == date(2026, 9, 17)


def test_morning_train_is_its_own_day():
    assert service_date(read_time("2609180600")) == date(2026, 9, 18)


def test_rows_record_which_file_they_came_from(tmp_path):
    """Without this the script cannot tell which files it already read."""
    path = write_xml(tmp_path, """
        <timetable station="Freiburg Hbf" eva="8000107">
          <s id="trip1"><ar pt="2609171605"/></s>
        </timetable>
    """.strip())

    rows = read_file(path)

    assert rows[0]["source"] == path
