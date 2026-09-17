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


def fetch(eva, headers):
    """Ask the API for all known changes at one station.

    Returns (status, body). Status is a number, or a short text on failure.
    """
    url = API + "/fchg/" + eva
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:
        return "error", str(e).encode()


def save(eva, body, now):
    """Write the response to a gzipped file, one folder per day."""
    day = now.strftime("%Y-%m-%d")
    folder = os.path.join(DATA_DIR, day)
    os.makedirs(folder, exist_ok=True)
    name = eva + "_" + now.strftime("%H%M%S") + ".xml.gz"
    path = os.path.join(folder, name)
    with gzip.open(path, "wb") as f:
        f.write(body)
    return path


def log(now, eva, status, size, records):
    """Add one line to the log file so we can see what was collected."""
    new_file = not os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        if new_file:
            f.write("time,eva,status,bytes,records\n")
        f.write("%s,%s,%s,%d,%d\n" % (now.isoformat(), eva, status, size, records))


def count_records(body):
    """Count stop records in the response.

    A reply can be valid but empty, so counting records tells us whether we
    really got data. Counting successful requests would not.
    """
    return body.count(b"<s id=")


def run_once(stations, headers):
    """Fetch every station once."""
    for eva, name in stations:
        now = datetime.now(timezone.utc)
        status, body = fetch(eva, headers)

        if status == 200:
            records = count_records(body)
            save(eva, body, now)
        else:
            records = 0

        log(now, eva, status, len(body), records)
        print("%s %-16s %s  %d records" % (now.strftime("%H:%M:%S"), name, status, records))

        if status == 401:
            print("Credentials rejected. Check .env")
            sys.exit(1)
        if status == 429:
            print("Rate limited. Waiting 60 seconds.")
            time.sleep(60)

        # Small gap so we stay well under the rate limit.
        time.sleep(1)


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
    while True:
        start = time.time()
        run_once(stations, headers)
        if once:
            return
        # Sleep the rest of the round.
        wait = ROUND_SECONDS - (time.time() - start)
        if wait > 0:
            time.sleep(wait)


if __name__ == "__main__":
    main()
