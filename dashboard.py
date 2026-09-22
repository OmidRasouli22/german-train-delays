"""Dashboard for the collected train delays.

Run it with:  streamlit run dashboard.py

It reads the small summary files in dashboard_data, not the collected
replies, so it works anywhere without the full archive.
"""

import os

import pandas as pd
import streamlit as st

DATA = "dashboard_data"

st.set_page_config(page_title="German Train Delays", page_icon="🚆",
                   layout="wide")


@st.cache_data
def load(name):
    return pd.read_parquet(os.path.join(DATA, name + ".parquet"))


def short(station):
    """Freiburg(Breisgau) Hbf is too long for a chart."""
    return station.replace("(Breisgau) ", " ")


st.title("German Train Delays")
st.caption(
    "Collected every two minutes from the Deutsche Bahn API. "
    "Eight stations in southern Germany."
)

if not os.path.exists(DATA):
    st.error("No data yet. Run export_dashboard_data.py first.")
    st.stop()

daily = load("station_daily")
daily["station"] = daily["station"].map(short)

# Let people pick which days to look at.
days = sorted(daily["service_date"].unique())
if len(days) > 1:
    first, last = st.select_slider(
        "Days", options=days, value=(days[0], days[-1]),
        format_func=lambda d: str(d))
    daily = daily[(daily["service_date"] >= first) & (daily["service_date"] <= last)]

# The numbers at the top.
scheduled = int(daily["scheduled"].sum())
on_time = int(daily["on_time"].sum())
cancelled = int(daily["cancelled"].sum())
ran = int(daily["ran"].sum())

a, b, c, d = st.columns(4)
a.metric("Stops", f"{scheduled:,}")
b.metric("On time", f"{100 * on_time / max(ran, 1):.1f}%",
         help="Under six minutes late, ignoring cancelled trains")
c.metric("Cancelled", f"{cancelled:,}")
d.metric("Days", f"{daily['service_date'].nunique()}")

st.divider()

left, right = st.columns(2)

with left:
    st.subheader("Punctuality by station")
    by_station = (daily.groupby("station")
                  .agg(on_time=("on_time", "sum"), ran=("ran", "sum"))
                  .assign(punctuality=lambda x: 100 * x.on_time / x.ran)
                  .sort_values("punctuality"))
    st.bar_chart(by_station["punctuality"], horizontal=True,
                 x_label="on time (%)", y_label="")

with right:
    st.subheader("Average delay by station")
    avg = (daily.assign(total=lambda x: x.avg_delay * x.ran)
           .groupby("station")
           .agg(total=("total", "sum"), ran=("ran", "sum"))
           .assign(avg=lambda x: x.total / x.ran)
           .sort_values("avg", ascending=False))
    st.bar_chart(avg["avg"], horizontal=True,
                 x_label="minutes late", y_label="")

st.divider()

left, right = st.columns(2)

with left:
    st.subheader("Through the day")
    by_hour = load("by_hour").set_index("hour")
    st.line_chart(by_hour["avg_delay"],
                  x_label="hour of day", y_label="minutes late")
    st.caption(
        "Delays are smallest early in the morning and grow all day. "
        "A late train makes the next one late, and it only resets overnight."
    )

with right:
    st.subheader("By kind of train")
    by_type = load("by_train_type").set_index("train_type")
    st.bar_chart(by_type["avg_delay"], x_label="", y_label="minutes late")
    st.caption(
        "Night trains cross several countries and collect delay the whole "
        "way. S-Bahn trains run short loops and stay close to the timetable."
    )

st.divider()

st.subheader("How the delays are spread out")
spread = load("spread")
spread["share"] = 100 * spread["stops"] / spread["stops"].sum()
st.bar_chart(spread.set_index("band")["share"],
             x_label="", y_label="share of stops (%)")
st.caption(
    "Most trains are fine. The ones people remember are the few that are "
    "more than half an hour late."
)

st.divider()

st.subheader("Day by day")
table = (daily[["service_date", "station", "scheduled", "on_time",
                "cancelled", "avg_delay", "punctuality"]]
         .sort_values(["service_date", "punctuality"]))
st.dataframe(table, use_container_width=True, hide_index=True)
