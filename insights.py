"""Team lead Insights: what is happening at THIS airline right now (queue, waiting time, workload, escalations, customers who wrote back).
Also shared chart helpers for the airline admin dashboard and the platform overview."""
import time

import pandas as pd
import streamlit as st

import auth, storage, ui
from common import esc, when
from ui import H

ss = st.session_state
DAY = 86400
INK, SOFT = "#0F1A2B", "#8FA3C4"


def month_key(ts):
    return time.strftime("%Y-%m", time.gmtime(ts))


def last_months(n=12):
    y, m = time.gmtime().tm_year, time.gmtime().tm_mon
    out = []
    for _ in range(n):
        out.append(f"{y}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def stat(n, label, dark=False):
    return f'<div class="stat {"dark" if dark else ""}"><div class="n">{n}</div><div class="l">{label}</div></div>'


def cards(items):
    """A row of KPI cards, followed by space so nothing sits against them."""
    cols = st.columns(len(items))
    for col, (n, label, dark) in zip(cols, items):
        with col:
            H(stat(n, label, dark))
    H('<div style="height:20px"></div>')


def box(title, sub=None):
    """A white bordered panel with a title; use as a context manager."""
    c = st.container(border=True)
    with c:
        H(f'<div style="font-weight:800;font-size:1.15rem">{esc(title)}</div>' + (f'<div class="muted" style="margin-bottom:6px">{esc(sub)}</div>' if sub else ""))
    return c


def bars(rows, fmt=lambda v: str(int(v)), empty="Nothing yet"):
    rows = [(k, v) for k, v in rows]
    if not rows or max(v for _, v in rows) == 0:
        return f'<div class="muted" style="padding:8px 0">{empty}</div>'
    return ui.hbars(rows, fmt=fmt, maxv=max(v for _, v in rows))


def hours(h):
    if h is None:
        return "n/a"
    return f"{h * 60:.0f} min" if h < 1 else (f"{h:.1f} h" if h < 48 else f"{h / 24:.1f} days")


def age_text(sec):
    m = int(sec // 60)
    return "just now" if m < 1 else (f"{m} min" if m < 120 else (f"{m // 60} h" if m < 2880 else f"{m // 1440} days"))


def first_reply_hours(items, since=0):
    v = [(i["resolved"] - i["created"]) / 3600 for i in items if i["status"] == "Approved" and i.get("resolved") and i["resolved"] >= since]
    return sum(v) / len(v) if v else None


def page_insights(org):
    if not ss.user or ss.user["role"] != auth.LEAD:
        st.error("Insights is available to team leads only.")
        return
    now = time.time()
    items = storage.items(org["id"])
    st.title("Insights")
    st.write(f"What is happening at {org['name']}: the queue, how long people wait, who is doing what, and what is coming back.")
    if not items:
        st.info("No complaints yet. Insights fill in as customers use your complaint form.")
        return
    open_ = [i for i in items if i["status"] in ("New", "Escalated")]
    esc_ = [i for i in items if i["status"] == "Escalated"]
    done = [i for i in items if i["status"] == "Approved"]
    oldest = max((now - i["created"] for i in open_), default=None)
    cards([(len(esc_), "Escalated, waiting for you", True), (len(open_), "Open complaints", False),
           (age_text(oldest) if oldest is not None else "none", "Oldest open complaint", False),
           (hours(first_reply_hours(items, now - 30 * DAY)), "Average time to first reply, last 30 days", False)])

    # --- volume and waiting time
    a, b = st.columns([1.5, 1], gap="large")
    with a:
        with box("Complaints in the last 14 days", "Received each day, and how many replies went out each day."):
            days = [time.strftime("%d %b", time.gmtime(now - k * DAY)) for k in range(13, -1, -1)]
            recv, sent = dict.fromkeys(days, 0), dict.fromkeys(days, 0)
            for i in items:
                k = time.strftime("%d %b", time.gmtime(i["created"]))
                if k in recv:
                    recv[k] += 1
                if i.get("resolved") and i["status"] == "Approved":
                    k2 = time.strftime("%d %b", time.gmtime(i["resolved"]))
                    if k2 in sent:
                        sent[k2] += 1
            st.bar_chart(pd.DataFrame({"Received": recv, "Replied": sent}), color=[INK, SOFT], stack=False, height=260)
    with b:
        with box("How long open complaints have waited", "Anything in the longer bars needs attention first."):
            edges = [("Under 1 hour", 0, 3600), ("1 to 4 hours", 3600, 14400), ("4 to 24 hours", 14400, DAY), ("1 to 3 days", DAY, 3 * DAY), ("Over 3 days", 3 * DAY, 10 ** 12)]
            H(bars([(n, sum(1 for i in open_ if lo <= now - i["created"] < hi)) for n, lo, hi in edges], empty="No open complaints. Nice."))
    st.write("")

    # --- reasons and reply speed by urgency
    recent = [i for i in items if now - i["created"] <= 30 * DAY]
    c, d = st.columns(2, gap="large")
    with c:
        with box("Main reasons for complaints, last 30 days", "What customers are unhappy about right now."):
            ser = pd.Series([i["reason_label"] for i in recent]).value_counts()
            H(bars(list(ser.items())[:8]))
    with d:
        with box("Time to first reply, by urgency", "Last 30 days. If High is not the shortest bar, urgent complaints are not being picked up first."):
            rows = []
            for lvl in ("High", "Medium", "Low", "Review"):
                h = first_reply_hours([i for i in items if i["category"] == lvl], now - 30 * DAY)
                if h is not None:
                    rows.append((ui.CAT_NAME[lvl], h))
            H(bars(rows, fmt=hours, empty="No replies in the last 30 days"))
    st.write("")

    # --- workload and people
    e, f = st.columns(2, gap="large")
    with e:
        with box("Open complaints by suggested team", "Where the work is piling up."):
            ser = pd.Series([i["team"] for i in open_]).value_counts()
            H(bars(list(ser.items()), empty="No open complaints"))
    with f:
        with box("Your agents, last 7 days", "Replies approved and complaints escalated, per person."):
            week = now - 7 * DAY
            people = [u for u in storage.users(org["id"]) if u["role"] in (auth.AGENT, auth.LEAD) and u["active"]]
            evs = [x for x in storage.events(org["id"], 5000) if x["ts"] >= week]
            rows = [{"Name": u["name"], "Role": u["role"],
                     "Replies sent": sum(1 for x in evs if x["action"] == "approved" and x["actor_id"] == u["id"]),
                     "Escalated": sum(1 for x in evs if x["action"] == "escalated" and x["actor_id"] == u["id"])} for u in people]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch") if rows else st.write("No agents yet.")
    st.write("")

    # --- escalations and customers coming back
    g, h_ = st.columns(2, gap="large")
    with g:
        with box("Customers who wrote back", "A reply that brings a follow-up may not have solved the problem."):
            wrote = [i for i in items if i.get("followups")]
            waiting = [i for i in wrote if i["status"] in ("New", "Escalated")]
            rate = f"{len(wrote) / len(done):.0%}" if done else "n/a"
            H(f'<div style="display:flex;gap:36px;margin:6px 0 2px"><div><div style="font-size:2rem;font-weight:800">{len(wrote)}</div><div class="muted">complaints with a follow-up</div></div>'
              f'<div><div style="font-size:2rem;font-weight:800">{rate}</div><div class="muted">of answered complaints</div></div>'
              f'<div><div style="font-size:2rem;font-weight:800">{len(waiting)}</div><div class="muted">waiting for a reply now</div></div></div>')
            ser = pd.Series([i["reason_label"] for i in wrote]).value_counts()
            if len(ser):
                H('<div class="muted" style="margin-top:10px">Reasons that most often bring a follow-up</div>' + bars(list(ser.items())[:5]))
    with h_:
        with box("Recent escalations", "Why agents passed complaints up."):
            evs = [x for x in storage.events(org["id"], 2000) if x["action"] == "escalated"][:6]
            if not evs:
                H('<div class="muted">No escalations yet.</div>')
            for x in evs:
                H(f'<div style="padding:8px 0;border-top:1px solid {ui.LINE}"><b>{esc(x["actor"])}</b> <span class="muted">· {when(x["ts"])} · {esc(x["ref"])}</span><div>{esc(x["detail"] or "no reason recorded")}</div></div>')
    st.caption("Times are UTC. Reply time counts from when the complaint arrived to the first approved reply.")
