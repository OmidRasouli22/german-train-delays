"""Make the charts used in the README."""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# The first afternoon has a gap in it, so it is left out.
START = "2026-09-17 20:00+02:00"
INK = "#333333"
BAR = "#4a6fa5"


def load():
    d = pd.read_parquet("stops.parquet")
    return d[d["planned"] >= START]


def style(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(colors=INK)
    ax.yaxis.label.set_color(INK)
    ax.xaxis.label.set_color(INK)
    ax.title.set_color(INK)


def by_hour(d):
    r = d[d["delay_minutes"].notna()]
    hourly = r.groupby(r["planned"].dt.hour)["delay_minutes"].mean()

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(hourly.index, hourly.values, color=BAR, linewidth=2)
    ax.fill_between(hourly.index, hourly.values, color=BAR, alpha=0.15)
    ax.set_xlabel("hour of day")
    ax.set_ylabel("average delay (minutes)")
    ax.set_title("Delays build up through the day")
    ax.set_xticks(range(0, 24, 2))
    ax.grid(axis="y", alpha=0.2)
    style(ax)
    fig.tight_layout()
    fig.savefig("charts/delay_by_hour.png", dpi=110)


def by_station(d):
    r = d[d["delay_minutes"].notna()]
    avg = r.groupby("station")["delay_minutes"].mean().sort_values()
    names = [s.replace("(Breisgau) ", " ") for s in avg.index]

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.barh(names, avg.values, color=BAR)
    ax.set_xlabel("average delay (minutes)")
    ax.set_title("Some stations are much worse than others")
    ax.grid(axis="x", alpha=0.2)
    style(ax)
    fig.tight_layout()
    fig.savefig("charts/delay_by_station.png", dpi=110)


def spread(d):
    r = d[d["delay_minutes"].notna()]
    bands = ["early", "on time", "1-5 min", "6-15 min", "16-30 min", "30+ min"]
    counts = [
        (r["delay_minutes"] < 0).sum(),
        (r["delay_minutes"] == 0).sum(),
        r["delay_minutes"].between(1, 5).sum(),
        r["delay_minutes"].between(6, 15).sum(),
        r["delay_minutes"].between(16, 30).sum(),
        (r["delay_minutes"] > 30).sum(),
    ]
    share = [100 * c / len(r) for c in counts]

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar(bands, share, color=BAR)
    ax.set_ylabel("share of stops (%)")
    ax.set_title("Most trains are fine. A few are very late.")
    for i, v in enumerate(share):
        ax.text(i, v + 0.7, "%.0f%%" % v, ha="center", color=INK, fontsize=9)
    ax.grid(axis="y", alpha=0.2)
    style(ax)
    fig.tight_layout()
    fig.savefig("charts/delay_spread.png", dpi=110)


def main():
    import os
    os.makedirs("charts", exist_ok=True)
    d = load()
    by_hour(d)
    by_station(d)
    spread(d)
    print("wrote 3 charts from %d stops" % len(d))


if __name__ == "__main__":
    main()
