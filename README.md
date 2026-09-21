# German Train Delays

Deutsche Bahn publishes what its trains are doing right now. A few minutes
later that information is gone, overwritten by the next update. Nobody can
tell you later what the board said this morning.

This project saves it, every two minutes, and turns it into tables you can
ask questions of.

Eight stations in southern Germany: Freiburg, Stuttgart, Karlsruhe, Mannheim,
Munich, Nuremberg, Ulm, Heidelberg.

## What the data shows

Delays are lowest at six in the morning and grow all day. A train in the
evening is three times later than the same train at dawn, because delays
pass from one train to the next and nothing resets until the night.

![Delay by hour](charts/delay_by_hour.png)

Where you stand matters more than when. Freiburg averages under three
minutes, Munich eight.

![Delay by station](charts/delay_by_station.png)

Most trains are fine. Three quarters arrive within five minutes. The ones
people remember are the four percent that are more than half an hour late.

![How delays are spread](charts/delay_spread.png)

Night trains are worst of all, around half an hour late on average, against
six minutes for ICE and under three for S-Bahn. They cross several countries
overnight and collect delay the whole way.

Numbers are from 22,930 stops collected between 17 and 21 September 2026.

## How it works

```
Deutsche Bahn API
       |
       |  every 2 minutes
       v
   collect.py  ---->  data/        saved replies, never changed
       |
       |  reads each file once
       v
    parse.py  ---->  events_*.parquet
       |
       v
      dbt      ---->  trains.duckdb
       |
       +-- stg_plan          the timetable
       +-- stg_changes       what really happened
       +-- fct_stop_delays   the two joined, with the delay worked out
```

### Collecting

The API answers two different questions and both are needed.

**The plan** is the timetable: what time a train is due. It changes once an
hour, so it is asked for once an hour.

**The changes** are what actually happened: the new arrival time. This is
asked for every two minutes because it keeps changing.

Neither is any use alone. The plan does not know about delays. The changes
usually give a new time without saying what the old one was. The delay only
appears when the two are put side by side.

### Saving replies as they arrive

`collect.py` saves the answer from the API exactly as it came, without
reading it. That looks lazy and is on purpose.

Reading the data is where mistakes happen. Early on, a disruption message was
read as a cancellation, which marked 1,349 trains as cancelled when they had
actually run. Fixing it took one command, because every original reply was
still on disk:

```
python parse.py --rebuild
```

If the collector had read the replies and saved only the result, those trains
would have been wrong forever.

### Working out the delay

The same train is fetched again every two minutes, so one stop shows up in
hundreds of files, each with a newer guess. Only the last one is true.

After that the timetable is joined to the changes. The join keeps every
planned train, including the ones that never appear in the changes at all,
because that silence means the train ran on time. Dropping them would delete
every punctual train and make the numbers look far worse than they are.

A cancelled train gets no delay. It was not late, it never ran.

## Running it

You need a free API key from
[developers.deutschebahn.com](https://developers.deutschebahn.com). Create an
account, create an application, then subscribe that application to the
Timetables API and pick the free plan. Creating the application is not enough
on its own, the subscription is a separate step.

```
pip install -r requirements.txt
cp .env.example .env
```

Put your client id and secret in `.env`, then:

```
python collect.py        collect, leave it running
python parse.py          build the table
python health.py         see what was collected and what is missing
python make_charts.py    redraw the charts
```

For the dbt models:

```
cd dbt
dbt deps
dbt run
dbt test
```

## Checking the collection

A collector that stops quietly is worse than one that crashes, because the
numbers built on top still look fine.

`health.py` shows every hour since collection started, how many rounds ran,
and how many records arrived. It counts records rather than successful
requests, because a reply can arrive with status 200 and hold nothing at all.

That is not a made up worry. While looking for a data source, one feed
answered every request successfully, with a valid reply and a fresh
timestamp, and no trains inside. A program checking only whether requests
succeeded would have reported everything was fine while saving nothing.

Collection so far is 2,655 rounds out of 2,820 expected. All the missing
hours are from one afternoon before the laptop was set not to sleep. Since
then it has not missed an hour.

## Tests

Two kinds, and they catch different things.

```
python -m pytest         29 tests, on every push
cd dbt && dbt test        8 tests, on the collected data
```

The python tests check the code: that a cancelled train gets no delay, that
the join never loses a planned train, that a delay over midnight is fifteen
minutes and not a negative day.

The dbt tests check the data itself: that no two rows describe the same stop,
that the columns everything depends on are filled in, that no delay is so
large it must be a misread time.

Both are needed. Every python test passed while the cancellation bug was in
the data, because they test the logic, not what the logic was fed.

The dbt tests need the collected files, so they run on the machine holding
the data. The python tests run in GitHub Actions on every push.

## Files

```
collect.py        asks the API and saves the replies
parse.py          turns saved replies into a table
health.py         shows what was collected and what is missing
make_charts.py    draws the charts above
queries.sql       questions, as plain SQL
ask.py            runs those questions
stations.txt      which stations to watch
dbt/              the same work as models, with tests
data/             the saved replies, about 150 MB a day
```

## Next

- Schedule the whole thing with Airflow
- A page showing punctuality per station per day
- Predict how late a train will be at its next stop
