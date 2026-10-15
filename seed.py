"""First-run setup: one platform admin, and one demo airline (Example Air) with staff and six months of sample history,
so the dashboards have something to show. Runs only when the database has no airlines yet."""
import os, random, threading, time
from pathlib import Path

import pandas as pd

import auth, storage, triage

ROOT = Path(__file__).parent


def _setting(name, default=None):
    v = os.environ.get(name)
    if v:
        return v
    try:
        import streamlit as st
        return st.secrets.get(name, default)
    except Exception:
        return default


def seed_history(al, n_old=160, n_new=15):
    """Older complaints are already answered (so the monthly and resolved figures mean something); the newest wait in the queue.
    Approvals are credited to the demo agent and team lead, a few were escalated first, and a few customers wrote back."""
    df = pd.read_csv(ROOT / "data" / "replay_sample.csv")
    rnd, n = random.Random(42), len(df)
    people = {u["role"]: u for u in storage.users(al["id"])}
    agent, lead = people.get(auth.AGENT), people.get(auth.LEAD)
    for i in range(n_old):
        text = str(df.text.iloc[i % n])
        age_min = int((0.1 + 13.9 * rnd.random()) * 1440) if i % 3 == 0 else int((3 + 172 * rnd.random() ** 0.85) * 1440) + rnd.randint(0, 1439)
        item = storage.add(al["id"], triage.mask(text), "Replayed tweet", "", triage.triage(text, al), age_min)
        escalated = rnd.random() < 0.09
        lo, hi = {"High": (15, 240), "Medium": (40, 600), "Low": (90, 1500), "Review": (200, 2400)}[item["category"]]  # urgent complaints are answered faster
        done_at = min(item["created"] + rnd.randint(lo, hi) * 60 + (rnd.randint(60, 900) * 60 if escalated else 0), time.time() - 60)
        who = lead if escalated and lead else (agent if rnd.random() < 0.8 or not lead else lead)
        storage.update(al["id"], item["id"], status="Approved", final_reply=item["draft"], resolved=done_at, approved_by=who["username"] if who else None)
        storage.log(al["id"], "customer", "customer", "received", item["ref"], "via Replayed tweet", ts=item["created"])
        if escalated and agent and lead:
            storage.log(al["id"], agent["name"], agent["role"], "escalated", item["ref"], "Customer asks for something I cannot approve", ts=done_at - 600, actor_id=agent["id"])
        if who:
            storage.log(al["id"], who["name"], who["role"], "approved", item["ref"], "sent as drafted", ts=done_at, actor_id=who["id"])
        if i % 14 == 0 and now_gap(done_at) > 1 * 86400:  # a few customers wrote back after the reply
            storage.add_message(al["id"], item["id"], "staff", item["draft"], who["username"] if who else "", ts=done_at)
            storage.add_message(al["id"], item["id"], "customer", "Thank you, but this still has not been sorted out. Please look at it again.", ts=done_at + 7200)
            storage.add_message(al["id"], item["id"], "staff", "Thank you for getting back to us. We have looked at it again and passed it to the team. " + al["sign_off"], who["username"] if who else "", ts=done_at + 20000)
            storage.log(al["id"], "customer", "customer", "follow_up", item["ref"], "customer wrote back", ts=done_at + 7200)
            with storage._conn() as c:
                c.execute("UPDATE complaints SET followups=1 WHERE id=?", (item["id"],))
    for j in range(n_new):
        text = str(df.text.iloc[(n_old + j) % n])
        it = storage.add(al["id"], triage.mask(text), "Replayed tweet", "", triage.triage(text, al), rnd.randint(1, 90))
        storage.log(al["id"], "customer", "customer", "received", it["ref"], "via Replayed tweet", ts=it["created"])


def now_gap(ts):
    return time.time() - ts


_LOCK = threading.Lock()


def default_admin_in_use() -> bool:
    """True while an active platform admin can still sign in with the published demo password."""
    return any(u["active"] and u["role"] == auth.PLATFORM_ADMIN and auth.verify(auth.DEMO_PASSWORD, u["pw"]) for u in storage.users())


def ensure_demo():
    if storage.airlines():
        return
    with _LOCK:  # two visitors on the very first run must not both set it up
        if storage.airlines():
            return
        _setup()


def _setup():
    admin_pw = _setting("PLATFORM_ADMIN_PASSWORD") or auth.DEMO_PASSWORD
    admin_user = (_setting("PLATFORM_ADMIN_USERNAME") or "admin.demo").strip().lower()
    storage.add_user(None, admin_user, "Nomsa D.", auth.PLATFORM_ADMIN, auth.hash_password(admin_pw), must_change=False, created_by="setup", email="admin@example.invalid")
    al = storage.add_airline("Example Air", sign_off="Example Air Customer Care", demo=True)
    demo_hash = auth.hash_password(auth.DEMO_PASSWORD)
    for username, name, role in (("org.demo", "Lerato N.", auth.ORG_ADMIN), ("lead.demo", "Sipho K.", auth.LEAD),
                                 ("agent.demo", "Thandi M.", auth.AGENT)):
        storage.add_user(al["id"], username, name, role, demo_hash, must_change=False, created_by="setup", email=f"{username}@example.invalid")
    if storage.count() == 0:
        seed_history(al)
    else:
        storage.adopt_orphans(al["id"])  # an older database file: keep its complaints under the demo airline
    storage.log(None, "setup", "", "airline_added", "", "Example Air (demo)")
