"""Show how much data was actually collected, and what is missing.

A pipeline that quietly stops is worse than one that fails loudly. This
reads the log and shows, hour by hour, how much was collected against how
much was expected.
"""

import csv
import sys
from collections import Counter
from datetime import datetime, timedelta

LOG_FILE = "collect_log.csv"

# One round fetches every station. At a round every two minutes that is
# 30 rounds an hour.
ROUNDS_PER_HOUR = 30


def read_log(path=LOG_FILE):
    """Read the log.

    Early rows were written before the plan was collected and have one
    column fewer. Both shapes are read here so old data still counts.

    old: time,eva,status,bytes,records
    new: time,kind,eva,status,bytes,records
    """
    rows = []
    with open(path, encoding="utf-8") as f:
        for parts in csv.reader(f):
            if not parts or parts[0] == "time":
                continue
            if len(parts) == 6:
                when, kind, _eva, status, _bytes, records = parts
            elif len(parts) == 5:
                when, _eva, status, _bytes, records = parts
                kind = "fchg"
            else:
                continue
            rows.append({
                "time": datetime.fromisoformat(when),
                "kind": kind,
                "status": status,
                "records": int(records or 0),
            })
    return rows


def hourly_counts(rows):
    """Count how many rounds and records landed in each hour."""
    rounds = Counter()
    records = Counter()
    stations = Counter()
    for row in rows:
        if row["kind"] != "fchg":
            continue
        # Drop the timezone so every hour is comparable.
        hour = row["time"].replace(minute=0, second=0, microsecond=0, tzinfo=None)
        rounds[hour] += 1
        records[hour] += row["records"]
        stations[hour] = max(stations[hour], 1)
    return rounds, records


def all_hours(first, last):
    """Every hour between the first and last, including empty ones."""
    hours = []
    hour = first
    while hour <= last:
        hours.append(hour)
        hour += timedelta(hours=1)
    return hours


def report(rows, station_count):
    rounds, records = hourly_counts(rows)
    if not rounds:
        print("No collection rows in the log yet.")
        return

    hours = all_hours(min(rounds), max(rounds))
    expected = ROUNDS_PER_HOUR * station_count

    print("hour              rounds  of %d   records" % ROUNDS_PER_HOUR)
    missing = 0
    for hour in hours:
        got = rounds.get(hour, 0) // station_count
        if got == 0:
            missing += 1
        bar = "#" * min(got, 30)
        print("%s   %4d           %7d  %s"
              % (hour.strftime("%Y-%m-%d %H:00"), got, records.get(hour, 0), bar))

    print()
    print("hours covered : %d" % (len(hours) - missing))
    print("hours missing : %d" % missing)

    total = sum(rounds.values())
    print("rounds        : %d of %d expected" % (total // station_count,
                                                 len(hours) * ROUNDS_PER_HOUR))

    bad = [r for r in rows if r["status"] != "200"]
    if bad:
        print("failed calls  : %d" % len(bad))

    # A reply can be fine and still hold nothing, so check records too.
    empty = [r for r in rows if r["status"] == "200" and r["records"] == 0]
    if empty:
        print("empty replies : %d  (status 200 but no trains)" % len(empty))


def main():
    try:
        rows = read_log()
    except FileNotFoundError:
        print("No log file yet. Run collect.py first.")
        return 1

    stations = sum(1 for line in open("stations.txt", encoding="utf-8")
                   if line.strip() and not line.startswith("#"))
    report(rows, stations)
    return 0


if __name__ == "__main__":
    sys.exit(main())
