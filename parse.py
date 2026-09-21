"""Read the saved files and build one table of train stops.

The API gives us two things. The plan says when a train should arrive.
The changes say when it actually arrived. Neither is much use alone, so
this joins them and works out how late each train was.

Run it any time. It reads everything from the start and rebuilds the table.
"""

import glob
import gzip
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

DATA_DIR = "data"
OUT_FILE = "stops.parquet"

# The API sends German local times. Keeping them German means an hour in the
# data is the hour a passenger stood on the platform.
GERMAN_TIME = ZoneInfo("Europe/Berlin")

# A train leaving at 00:30 belongs to the day before. Railways count the day
# as running past midnight, so nights are not split in two.
SERVICE_DAY_STARTS_AT = 3


def read_time(text):
    """Turn an API time like 2609171605 into a real date and time.

    The clock changes twice a year. Saying which timezone this is means an
    hour before the October change and an hour after it still line up.
    """
    if not text:
        return None
    return datetime.strptime(text, "%y%m%d%H%M").replace(tzinfo=GERMAN_TIME)


def service_date(when):
    """Which day of service a time belongs to.

    Anything before 03:00 counts as the day before, so a train running at
    00:30 stays with the evening it started in.
    """
    if when is None or pd.isna(when):
        return None
    if when.hour < SERVICE_DAY_STARTS_AT:
        return (when - timedelta(days=1)).date()
    return when.date()


def read_file(path):
    """Pull the stop events out of one saved file.

    Each file holds many trains. Each train can have an arrival, a
    departure, or both. We make one row per event.
    """
    with gzip.open(path, "rb") as f:
        text = f.read().decode("utf-8")

    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []

    station = root.get("station")
    fetched = file_time(path)
    rows = []

    for stop in root.findall("s"):
        stop_id = stop.get("id")

        # Train details are only in the plan files.
        train = stop.find("tl")
        train_type = train.get("c") if train is not None else None
        train_number = train.get("n") if train is not None else None

        for kind in ("ar", "dp"):
            event = stop.find(kind)
            if event is None:
                continue

            # cs="c" on the arrival or departure means this stop was
            # cancelled. The <m> messages are about disruptions and say
            # nothing about whether the train ran.
            cancelled = event.get("cs") == "c"

            rows.append({
                "stop_id": stop_id,
                "eva": root.get("eva") or eva_from_path(path),
                "station": station,
                "event": "arrival" if kind == "ar" else "departure",
                "planned": read_time(event.get("pt")),
                "actual": read_time(event.get("ct")),
                "line": event.get("l"),
                "planned_platform": event.get("pp"),
                "actual_platform": event.get("cp"),
                "train_type": train_type,
                "train_number": train_number,
                "cancelled": cancelled,
                "fetched": fetched,
                "source": path,
            })

    return rows


def file_time(path):
    """Get the time we fetched a file from its name and folder."""
    name = os.path.basename(path)
    day = os.path.basename(os.path.dirname(path))
    clock = name.split("_")[1].split(".")[0]
    return datetime.strptime(day + clock, "%Y-%m-%d%H%M%S")


def eva_from_path(path):
    """Get the station number from the file name."""
    return os.path.basename(path).split("_")[0]


def cache_file(kind):
    """Where the events read out of the saved files are kept."""
    return "events_%s.parquet" % kind


def read_all(kind, rebuild=False):
    """Read the saved files of one kind into a table.

    Files never change once written, so a file only needs reading once. The
    events are kept in a parquet file and only new files are read after that.
    Pass rebuild to read everything again, which is what you want after
    changing how a file is read.
    """
    paths = sorted(glob.glob(os.path.join(DATA_DIR, kind, "*", "*.xml.gz")))

    old = pd.DataFrame()
    done = set()
    if not rebuild and os.path.exists(cache_file(kind)):
        old = pd.read_parquet(cache_file(kind))
        done = set(old["source"])

    new_paths = [p for p in paths if p not in done]

    rows = []
    for path in new_paths:
        rows.extend(read_file(path))

    new = pd.DataFrame(rows)
    events = pd.concat([old, new], ignore_index=True) if len(new) else old

    if len(new):
        events.to_parquet(cache_file(kind), index=False)

    print("%s: %d files (%d new), %d events"
          % (kind, len(paths), len(new_paths), len(events)))
    return events


def latest_only(table, columns):
    """Keep the newest version of each event.

    The same train is fetched again every two minutes, so we see it many
    times. We want the last thing the API said about it.
    """
    table = table.sort_values("fetched")
    return table.drop_duplicates(subset=columns, keep="last")


def build_stops(plan, changes):
    """Join the timetable to the changes and work out the delays.

    One row per train stop. A planned stop with no change ran on time.
    """
    key = ["stop_id", "event"]

    # Keep the newest copy of each stop from both sides.
    plan = latest_only(plan, key)
    plan = plan[["stop_id", "event", "eva", "station", "planned", "line",
                 "planned_platform", "train_type", "train_number"]]

    changes = latest_only(changes, key)
    changes = changes[["stop_id", "event", "actual", "actual_platform", "cancelled"]]

    stops = plan.merge(changes, on=key, how="left")
    stops["cancelled"] = stops["cancelled"].fillna(False).astype(bool)

    # Which day of service the stop belongs to.
    stops["service_date"] = stops["planned"].map(service_date)

    # How late the train was, in minutes. Both times carry a timezone, so
    # the clock change in October does not turn into a one hour delay.
    late = (stops["actual"] - stops["planned"]).dt.total_seconds() / 60
    stops["delay_minutes"] = late.fillna(0).round().astype(int)

    # A cancelled train is not late. It never ran.
    stops.loc[stops["cancelled"], "delay_minutes"] = None

    return stops


def main():
    # Reading a saved file again is only needed if this script changed.
    rebuild = "--rebuild" in sys.argv

    plan = read_all("plan", rebuild)
    changes = read_all("fchg", rebuild)

    if plan.empty:
        print("No plan files yet. Let the collector run for an hour.")
        return

    stops = build_stops(plan, changes)
    stops.to_parquet(OUT_FILE, index=False)

    print()
    print("Wrote %s with %d stops." % (OUT_FILE, len(stops)))
    print("Cancelled: %d" % stops["cancelled"].sum())
    ran = stops[~stops["cancelled"]]
    if len(ran):
        on_time = (ran["delay_minutes"] < 6).sum()
        print("On time (under 6 min): %d of %d, %.0f%%"
              % (on_time, len(ran), 100 * on_time / len(ran)))


if __name__ == "__main__":
    main()
