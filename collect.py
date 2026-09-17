"""Fetch train delay data from the DB Timetables API and save it to disk.

Saves the raw XML exactly as it arrives. Parsing happens later, so that a
mistake in parsing can be fixed by re-reading the saved files.
"""

import gzip
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

API = "https://apis.deutschebahn.com/db-api-marketplace/apis/timetables/v1"
DATA_DIR = "data"
LOG_FILE = "collect_log.csv"

# Wait this long between rounds. The API allows 60 calls a minute.
ROUND_SECONDS = 120


def read_env(path=".env"):
    """Read KEY=VALUE lines from the .env file."""
    values = {}
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def read_stations(path="stations.txt"):
    """Read the station list. Returns a list of (eva, name)."""
    stations = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            eva, name = line.split(" ", 1)
            stations.append((eva, name))
    return stations


def fetch(url, headers):
    """Call the API. Returns (status, body).

    Status is a number, or a short text on failure.
    """
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        return "error", str(e).encode()


def save(kind, eva, body, now):
    """Write the response to a gzipped file, one folder per day and kind."""
    day = now.strftime("%Y-%m-%d")
    folder = os.path.join(DATA_DIR, kind, day)
    os.makedirs(folder, exist_ok=True)
    name = eva + "_" + now.strftime("%H%M%S") + ".xml.gz"
    path = os.path.join(folder, name)
    with gzip.open(path, "wb") as f:
        f.write(body)
    return path


def log(now, kind, eva, status, size, records):
    """Add one line to the log file so we can see what was collected."""
    new_file = not os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        if new_file:
            f.write("time,kind,eva,status,bytes,records\n")
        f.write("%s,%s,%s,%s,%d,%d\n" % (now.isoformat(), kind, eva, status, size, records))


def count_records(body):
    """Count stop records in the response.

    A reply can be valid but empty, so counting records tells us whether we
    really got data. Counting successful requests would not.
    """
    return body.count(b"<s id=")


def collect(kind, url, eva, name, headers):
    """Fetch one thing, save it, log it."""
    now = datetime.now(timezone.utc)
    status, body = fetch(url, headers)

    if status == 200:
        records = count_records(body)
        save(kind, eva, body, now)
    else:
        records = 0

    log(now, kind, eva, status, len(body), records)
    print("%s %-5s %-16s %s  %d records"
          % (now.strftime("%H:%M:%S"), kind, name, status, records))

    if status == 401:
        print("Credentials rejected. Check .env")
        sys.exit(1)
    if status == 429:
        print("Rate limited. Waiting 60 seconds.")
        time.sleep(60)

    # Small gap so we stay well under the rate limit.
    time.sleep(1)


def run_once(stations, headers, with_plan):
    """Fetch every station once.

    Changes are fetched every round. The plan only changes once an hour,
    so it is fetched less often.
    """
    for eva, name in stations:
        collect("fchg", API + "/fchg/" + eva, eva, name, headers)

    if with_plan:
        now = datetime.now()
        day = now.strftime("%y%m%d")
        hour = now.strftime("%H")
        for eva, name in stations:
            url = "%s/plan/%s/%s/%s" % (API, eva, day, hour)
            collect("plan", url, eva, name, headers)


def main():
    env = read_env()
    headers = {
        "DB-Client-Id": env["DB_CLIENT_ID"],
        "DB-Api-Key": env["DB_CLIENT_SECRET"],
        "Accept": "application/xml",
    }
    stations = read_stations()
    print("Collecting %d stations every %d seconds. Ctrl+C to stop." % (len(stations), ROUND_SECONDS))

    once = "--once" in sys.argv
    last_plan_hour = None

    while True:
        start = time.time()

        # Get the plan once per hour, changes every round.
        this_hour = datetime.now().strftime("%Y%m%d%H")
        with_plan = this_hour != last_plan_hour
        run_once(stations, headers, with_plan)
        if with_plan:
            last_plan_hour = this_hour

        if once:
            return
        # Sleep the rest of the round.
        wait = ROUND_SECONDS - (time.time() - start)
        if wait > 0:
            time.sleep(wait)


if __name__ == "__main__":
    main()
