# German Train Delays

Collects live train delay data from Deutsche Bahn and turns it into tables you
can ask questions of, like "which station has the worst delays on a Monday
morning?"

The data is only available right now. If nobody saves it, it is gone. So the
first part of this project is a small program that keeps saving it.

## What it does so far

`collect.py` asks the Deutsche Bahn API what is happening at eight stations in
southern Germany, and saves the answer to a file. It does this every two
minutes, all day.

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
stations.txt      which stations to watch
.env              your API keys (never goes to GitHub)
data/             the saved files
collect_log.csv   what was collected and when
```

Files are saved as `data/2026-09-17/8000096_115833.xml.gz`. That is the
station number and the time, gzipped to save space.

About 170 MB a day.

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

## Next

- Read the saved files and turn them into a table
- Work out the real delay for each train at each stop
- Build daily punctuality numbers
