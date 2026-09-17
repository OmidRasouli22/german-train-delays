"""Read the saved files and build one table of train stops.

The API gives us two things. The plan says when a train should arrive.
The changes say when it actually arrived. Neither is much use alone, so
this joins them and works out how late each train was.

Run it any time. It reads everything from the start and rebuilds the table.
"""

import glob
import gzip
import os
import xml.etree.ElementTree as ET
from datetime import datetime

import pandas as pd

DATA_DIR = "data"
OUT_FILE = "stops.parquet"


def read_time(text):
    """Turn an API time like 2609171605 into a real date and time."""
    if not text:
        return None
    return datetime.strptime(text, "%y%m%d%H%M")


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

        # A message with t="c" means the train was cancelled.
        cancelled = any(m.get("t") == "c" for m in stop.findall("m"))

        # Train details are only in the plan files.
        train = stop.find("tl")
        train_type = train.get("c") if train is not None else None
        train_number = train.get("n") if train is not None else None

        for kind in ("ar", "dp"):
            event = stop.find(kind)
            if event is None:
                continue

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


def read_all(kind):
    """Read every saved file of one kind into a table."""
    paths = sorted(glob.glob(os.path.join(DATA_DIR, kind, "*", "*.xml.gz")))
    rows = []
    for path in paths:
        rows.extend(read_file(path))
    print("%s: %d files, %d events" % (kind, len(paths), len(rows)))
    return pd.DataFrame(rows)


def latest_only(table, columns):
    """Keep the newest version of each event.

    The same train is fetched again every two minutes, so we see it many
    times. We want the last thing the API said about it.
    """
    table = table.sort_values("fetched")
    return table.drop_duplicates(subset=columns, keep="last")


def main():
    plan = read_all("plan")
    changes = read_all("fchg")

    if plan.empty:
        print("No plan files yet. Let the collector run for an hour.")
        return

    key = ["stop_id", "event"]

    # The plan gives the timetable. Keep the newest copy of each stop.
    plan = latest_only(plan, key)
    plan = plan[["stop_id", "event", "eva", "station", "planned", "line",
                 "planned_platform", "train_type", "train_number"]]

    # The changes give the real times. Again keep the newest.
    changes = latest_only(changes, key)
    changes = changes[["stop_id", "event", "actual", "actual_platform", "cancelled"]]

    # Join them. A planned stop with no change ran on time.
    stops = plan.merge(changes, on=key, how="left")
    stops["cancelled"] = stops["cancelled"].fillna(False).astype(bool)

    # How late the train was, in minutes. Empty if we do not know yet.
    late = (stops["actual"] - stops["planned"]).dt.total_seconds() / 60
    stops["delay_minutes"] = late.fillna(0).round().astype(int)
    stops.loc[stops["cancelled"], "delay_minutes"] = None

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
