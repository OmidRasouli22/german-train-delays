"""Tests for the collection health report."""

from datetime import datetime

from health import all_hours, hourly_counts, read_log


def write_log(tmp_path, text):
    path = tmp_path / "log.csv"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_reads_new_format(tmp_path):
    path = write_log(tmp_path, """time,kind,eva,status,bytes,records
2026-09-17T20:00:00+00:00,fchg,8000107,200,1000,268
""")

    rows = read_log(path)

    assert rows[0]["kind"] == "fchg"
    assert rows[0]["status"] == "200"
    assert rows[0]["records"] == 268


def test_reads_old_format_without_kind(tmp_path):
    """Early rows have one column fewer. They are all changes."""
    path = write_log(tmp_path, """time,eva,status,bytes,records
2026-09-17T12:00:00+00:00,8000107,200,1000,268
""")

    rows = read_log(path)

    assert rows[0]["kind"] == "fchg"
    assert rows[0]["status"] == "200"
    assert rows[0]["records"] == 268


def test_plan_rows_are_not_counted_as_rounds(tmp_path):
    """Only the changes run every two minutes, so only they measure uptime."""
    path = write_log(tmp_path, """time,kind,eva,status,bytes,records
2026-09-17T20:00:00+00:00,fchg,8000107,200,1000,10
2026-09-17T20:00:01+00:00,plan,8000107,200,1000,25
""")

    rounds, records = hourly_counts(read_log(path))

    assert sum(rounds.values()) == 1
    assert sum(records.values()) == 10


def test_all_hours_includes_the_gap():
    """An hour with no data still has to appear, or a gap stays invisible."""
    first = datetime(2026, 9, 17, 12)
    last = datetime(2026, 9, 17, 15)

    hours = all_hours(first, last)

    assert len(hours) == 4
    assert datetime(2026, 9, 17, 13) in hours


def test_counts_land_in_the_right_hour(tmp_path):
    path = write_log(tmp_path, """time,kind,eva,status,bytes,records
2026-09-17T20:59:00+00:00,fchg,8000107,200,1000,5
2026-09-17T21:01:00+00:00,fchg,8000107,200,1000,7
""")

    rounds, records = hourly_counts(read_log(path))

    assert records[datetime(2026, 9, 17, 20)] == 5
    assert records[datetime(2026, 9, 17, 21)] == 7
