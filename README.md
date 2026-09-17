# German Train Delays

Collects live train delay data from Deutsche Bahn and turns it into tables you
can ask questions of, like "which station has the worst delays on a Monday
morning?"

The data is only available right now. If nobody saves it, it is gone. So the
first part of this project is a small program that keeps saving it.

## What it does so far

`collect.py` asks the Deutsche Bahn API about eight stations in southern
Germany and saves the answers. It runs all day.

`parse.py` reads those saved files and builds a table of train stops with
how late each one was.

Stations: Freiburg, Stuttgart, Karlsruhe, Mannheim, Munich, Nuremberg, Ulm,
Heidelberg.

## Setup

You need a free API key from
[developers.deutschebahn.com](https://developers.deutschebahn.com).
Create an account, create an application, then subscribe that application to
the "Timetables" API and pick the free plan.

Copy your keys into a file called `.env`:

```
cp .env.example .env
```

Then edit `.env` and paste in your client id and secret.

## Running it

Test that it works:

```
python collect.py --once
```

You should see eight lines, one per station, each with a number of records.

Leave it running:

```
python collect.py
```

Stop it with Ctrl+C.

## Where things go

```
collect.py        the collector
parse.py          turns saved files into a table
stations.txt      which stations to watch
.env              your API keys (never goes to GitHub)
data/             the saved files
stops.parquet     the table
collect_log.csv   what was collected and when
```

Files are saved as `data/fchg/2026-09-17/8000096_115833.xml.gz`. That is the
station number and the time, gzipped to save space.

About 170 MB a day.

## Two kinds of file

The API answers two different questions and we need both.

`plan` is the timetable: when a train is supposed to arrive. It only changes
once an hour, so we ask for it once an hour.

`fchg` is what changed: when the train will actually arrive. We ask every two
minutes because it keeps changing.

Neither is useful alone. The plan does not know about delays. The changes
often give a new time without saying what the old one was. Joining them is
what produces a delay.

## Why the files are saved raw

The collector saves the answer from the API exactly as it arrives, without
reading it. That seems lazy but it is on purpose.

Later, the data gets read and turned into tables. That reading step will have
mistakes in it. When a mistake is found, the saved files can be read again
with the fixed code. Nothing is lost.

If the collector read the data itself and saved only the result, a mistake
would be permanent.

## One thing that surprised me

A reply from a server can say "OK" and contain nothing at all.

While looking for a data source I found one that answered every request
successfully, with a valid response and a fresh timestamp, and zero trains
inside. A program checking only whether requests succeeded would have reported
everything was fine while saving nothing.

So the log counts records, not successful requests.

## Making the table

```
python parse.py
```

This reads every file saved so far and writes `stops.parquet`. One row is one
train at one station, either arriving or leaving, with how many minutes late
it was.

It reads everything from scratch each time. That is slower but it means a
mistake in this script can be fixed and the table rebuilt correctly, because
the saved files never change.

## Next

- Load the table into DuckDB and ask questions of it
- Daily punctuality per station
- A dashboard
