import json, random, time
from pathlib import Path
import pandas as pd
import streamlit as st
import admin_pages, auth, insights, llm, seed, storage, triage, ui
from common import ACTION_LABELS, audit, esc, flash, md_esc, sign_out, when, airline_links
from ui import H

ROOT = Path(__file__).parent
METRICS = json.load(open(ROOT / "model" / "metrics.json"))
ss = st.session_state

seed.ensure_demo()  # first run only: platform admin + the Example Air demo airline

# Which airline's link was used, and what kind of page was asked for
SLUG = st.query_params.get("airline")
VIEW = st.query_params.get("view")
PUBLIC = VIEW in ("form", "status")
LINK_ORG = storage.airline_by_slug(SLUG) if SLUG else None
st.set_page_config(page_title=LINK_ORG["name"] if (PUBLIC and LINK_ORG) else f"{ui.APP_NAME}: complaint triage", page_icon="✈", layout="wide")
H(ui.BASE_CSS)

ORDER = {"High": 0, "Medium": 1, "Low": 2, "Review": 3}
IDLE_SECONDS = 3600  # signed out after an hour without a click
if ss.get("user"):
    # Keep the signed-in person's account fresh: switching a user or an airline off, or resetting their password, takes effect on their next click
    _fresh = storage.user_by_id(ss.user["id"])
    _org = storage.airline(_fresh["airline_id"]) if _fresh and _fresh["airline_id"] else None
    if not _fresh or not _fresh["active"] or (_fresh["airline_id"] and (not _org or not _org["active"])):
        sign_out("Your access has been switched off. Please contact your administrator.")
    elif _fresh["pw"] != ss.get("pw_seen"):
        sign_out("Your password was changed, so please sign in again.")
    elif time.time() - ss.get("last_seen", 0) > IDLE_SECONDS:
        sign_out("You were signed out after an hour of inactivity.")
    else:
        ss.user = _fresh
        ss.last_seen = time.time()
ss.setdefault("user", None)
ss.setdefault("page", "login")
ss.setdefault("fails", 0)
ss.setdefault("last_fail", 0.0)
ss.setdefault("selected", None)
ss.setdefault("filter", "All")
STAFF_ORG = storage.airline(ss.user["airline_id"]) if ss.user and ss.user["airline_id"] else None
ORG = LINK_ORG if PUBLIC else (STAFF_ORG or LINK_ORG)  # the airline this screen is about (None for the platform admin)

HOME = {auth.PLATFORM_ADMIN: "overview", auth.ORG_ADMIN: "dashboard", auth.LEAD: "insights", auth.AGENT: "queue"}
ALLOWED = {auth.PLATFORM_ADMIN: {"overview", "airlines", "allusers", "platlog", "system", "password"},
           auth.ORG_ADMIN: {"dashboard", "staff", "activity", "password"},
           auth.LEAD: {"queue", "insights", "activity", "password"},
           auth.AGENT: {"queue", "password"}}
NAV = {auth.PLATFORM_ADMIN: [("Overview", "overview", "dashboard"), ("Airlines", "airlines", "flight"), ("All users", "allusers", "group"),
                             ("Platform log", "platlog", "history"), ("System", "system", "monitor_heart")],
       auth.ORG_ADMIN: [("Dashboard", "dashboard", "dashboard"), ("Staff", "staff", "group"), ("Activity log", "activity", "history")],
       auth.LEAD: [("Queue", "queue", "inbox"), ("Insights", "insights", "insights"), ("Activity log", "activity", "history")],
       auth.AGENT: [("Queue", "queue", "inbox")]}


# ---------- shared store (SQLite: every session sees the same queue) ----------
@st.cache_resource
def replay_state():
    return {"df": pd.read_csv(ROOT / "data" / "replay_sample.csv"), "pos": 200}


def _add(text, source, flight="", age_min=0):
    t = triage.triage(text, ORG)
    item = storage.add(ORG["id"], triage.mask(text), source, flight, t, age_min)
    who = ("customer", "customer") if source == "Customer form" else ("system", "replay")
    storage.log(ORG["id"], who[0], who[1], "received", item["ref"], f"via {source}")
    return item


def _replay(n):
    if not ORG or not ORG["demo"]:
        return
    r = replay_state()
    for _ in range(n):
        row = r["df"].iloc[r["pos"] % len(r["df"])]
        r["pos"] += 1
        _add(str(row.text), "Replayed tweet", age_min=random.randint(1, 90))


def age(item):
    m = int((time.time() - item["created"]) // 60)
    return "just now" if m < 1 else (f"{m} min" if m < 120 else f"{m // 60} h")


def go(p):
    ss.page = p
    ss.reveal = None  # a one-time password is not kept once the admin moves on
    if p != "status" and "ref" in st.query_params:
        del st.query_params["ref"]  # the reference only travels with the status page
    if p in ("form", "status"):
        st.query_params["view"] = p
    elif "view" in st.query_params:
        del st.query_params["view"]


def fill_demo(name):
    ss.login_user, ss.login_pass = name, auth.DEMO_PASSWORD


# ---------- sidebar ----------
def nav(label, page, icon):
    st.button(f":material/{icon}: {label}", key=f"nav_{page}", on_click=go, args=(page,),
              width="stretch", type="primary" if ss.page == page else "secondary")


def sidebar():
    role = ss.user["role"]
    with st.sidebar:
        H(f'<div style="padding:4px 8px 24px">{ui.brand(dark=False, org=ORG["name"] if ORG else None, platform=role == auth.PLATFORM_ADMIN)}</div>')
        queue_role = role in (auth.AGENT, auth.LEAD)
        if queue_role:
            items = storage.items(ORG["id"])
            waiting = [i for i in items if i["status"] == "New"]
            escalated = [i for i in items if i["status"] == "Escalated"]
            mine_open = waiting + (escalated if role == auth.LEAD else [])  # the lead's queue includes what was escalated to them
            n_high = sum(1 for i in mine_open if i["category"] == "High")
            n_rev = sum(1 for i in mine_open if i["category"] == "Review")
            n_done = sum(1 for i in items if i["status"] == "Approved")
            H(f"<style>.st-key-nav_queue button::after{{content:'{len(mine_open)}';margin-left:auto;background:#fff;border:1px solid #E3E7EC;border-radius:999px;padding:1px 10px;font-size:13px;font-weight:700;color:#344054}}</style>")
        H('<div class="sb-label">WORKSPACE</div>')
        for label, page, icon in NAV[role]:
            nav(label, page, icon)
        if queue_role:
            H(f"""<div style="height:18px"></div><div class="sb-label">TODAY</div>
<div class="sb-row"><span class="dot" style="background:{ui.CAT['High'][0]}"></span>Need a reply first<b>{n_high}</b></div>
<div class="sb-row"><span class="dot" style="background:{ui.CAT['Review'][0]}"></span>Need checking<b>{n_rev}</b></div>
<div class="sb-row"><span class="dot" style="background:{ui.DARK2}"></span>Replies approved<b>{n_done}</b></div>""" + (f'<div class="sb-row"><span class="dot" style="background:#6B7C8C"></span>Escalated to you<b>{sum(1 for i in items if i["status"] == "Escalated")}</b></div>' if role == auth.LEAD else ""))
        with st.container(key="sbfoot"):
            ini = "".join(w[0] for w in ss.user["name"].split()[:2])
            H(f"""<div class="sb-user"><div class="sb-av">{esc(ini)}</div>
<div><div class="sb-name">{esc(ss.user['name'])}</div><div class="sb-role">{esc(role)}</div></div></div>""")
            c1, c2 = st.columns(2)
            c1.button(":material/key:", key="nav_password", on_click=go, args=("password",), help="Change password", width="stretch")
            if c2.button(":material/logout:", key="signout", help="Sign out", width="stretch"):
                audit("signed_out")
                sign_out()
                st.rerun()
            H('<div class="sb-note">Prototype with sample data. Handles are masked. Customers only see replies on their status page.</div>')


# ---------- sign-in ----------
def page_login():
    H(ui.LOGIN_CSS)
    org = LINK_ORG
    left, right = st.columns([1.15, 1], gap="small")
    with left:
        headline = "Every complaint, sorted before you open it." if org else "One place to run complaint triage for every airline."
        sub = ("See who needs you first, why the app thinks so, and a draft reply to check. A person always decides." if org else
               "Add airlines, look after their accounts, and keep the system healthy.")
        H(f"""<div class="hero">{ui.brand(org=org["name"] if org else None, platform=not org)}
<h2>{headline}</h2>
<p>{sub}</p>
<div class="float">
<div class="row">{ui.chip("High")}<div><div class="t">Flight cancelled, stuck with two kids</div><div class="s">Cancelled Flight, 91% sure, to Operations</div></div></div>
<div class="row">{ui.chip("Medium")}<div><div class="t">Can't change my booking online</div><div class="s">Booking Problems, 74% sure, to Reservations</div></div></div>
<div class="row">{ui.chip("Review")}<div><div class="t">Very disappointed with the whole trip</div><div class="s">Only 31% sure, so a person checks it</div></div></div>
</div>
<svg class="arc" width="520" height="420" viewBox="0 0 520 420" fill="none"><circle cx="300" cy="300" r="260" stroke="#8FA3C4" stroke-opacity=".28" stroke-width="2" stroke-dasharray="3 10"/><circle cx="300" cy="300" r="190" stroke="#8FA3C4" stroke-opacity=".2" stroke-width="2"/><circle cx="300" cy="300" r="120" fill="#1C2B40"/><path d="M60 330 C140 150 260 90 430 70" stroke="#8FA3C4" stroke-width="2.5" stroke-dasharray="2 9" stroke-linecap="round"/><circle cx="60" cy="330" r="7" fill="#8FA3C4"/></svg>
</div>""")
    with right:
        if SLUG and not org:
            st.title("Link not recognised")
            st.write("Check the link you were given, or ask your platform administrator for the right one.")
            return
        if org and not org["active"]:
            st.title("Access switched off")
            st.write(f"{org['name']} is not using Tower right now. Please contact your platform administrator.")
            return
        st.title("Welcome back")
        st.write(f"Sign in to {org['name']}." if org else "Platform sign-in.")
        if org and org["demo"]:
            c1, c2, c3 = st.columns(3)
            c1.button(":material/support_agent: Agent", on_click=fill_demo, args=("agent.demo",), width="stretch")
            c2.button(":material/leaderboard: Team lead", on_click=fill_demo, args=("lead.demo",), width="stretch")
            c3.button(":material/admin_panel_settings: Airline admin", on_click=fill_demo, args=("org.demo",), width="stretch")
            st.caption("Demo buttons. Agent works the queue. Team lead starts on Insights and decides escalations. Airline admin sees the dashboard and manages staff.")
        elif seed.default_admin_in_use():
            st.button(":material/shield_person: Platform admin demo", on_click=fill_demo, args=("admin.demo",), width="stretch")
        left_s = auth.locked_for(ss.fails, ss.last_fail)
        with st.form("login", border=False):
            u = st.text_input("Username", key="login_user")
            p = st.text_input("Password", type="password", key="login_pass")
            go_ = st.form_submit_button("Sign in", type="primary", width="stretch")
        if go_ and not left_s:
            typed = storage.user_by_username(u)
            found = auth.check(u, p)
            right_place = bool(found) and ((org is not None and found["airline_id"] == org["id"]) or (org is None and found["role"] == auth.PLATFORM_ADMIN))
            if right_place:
                storage.clear_failed_logins(found["id"])
                ss.user, ss.fails = found, 0
                ss.pw_seen, ss.last_seen = found["pw"], time.time()
                storage.log(found["airline_id"], found["name"], found["role"], "signed_in", actor_id=found["id"])
                ss.page = HOME[found["role"]]
                st.rerun()
            ss.fails += 1
            ss.last_fail = time.time()
            if typed and not found and not auth.is_locked(typed) and not auth.verify(p, typed["pw"]):
                storage.note_failed_login(typed["id"])  # lock the account itself after repeated wrong passwords
            # Log the username only when it belongs to the place being signed in to, never the password.
            mine = typed and ((org is not None and typed["airline_id"] == org["id"]) or (org is None and typed["role"] == auth.PLATFORM_ADMIN))
            storage.log(typed["airline_id"] if mine else (org["id"] if org else None), typed["username"] if mine else "unknown user", "", "sign_in_failed")
            left_s = auth.locked_for(ss.fails, ss.last_fail)
            st.error("The username or password is not correct, or the account is locked for a few minutes." + ("" if org else " Airline staff: use the sign-in link your administrator gave you."))
        if left_s:
            st.warning(f"Too many tries. Wait {left_s} seconds and try again.")
        if org:
            st.divider()
            st.write("Are you a customer?")
            d1, d2 = st.columns(2)
            d1.button("Send a complaint", on_click=go, args=("form",), width="stretch")
            d2.button("Check progress", on_click=go, args=("status",), width="stretch")
        else:
            demo = [a for a in storage.airlines() if a["demo"] and a["active"]]
            if demo:
                st.divider()
                st.write("Want to see an airline's side?")
                st.markdown(f"[Open the {demo[0]['name']} demo airline](?airline={demo[0]['slug']})")


def page_password():
    forced = ss.user["must_change"]
    st.title("Choose a new password" if forced else "Change your password")
    if ss.user["created_by"] == "setup" and ss.user["role"] != auth.PLATFORM_ADMIN:
        st.info("This is a shared demo account, so its password cannot be changed.")
        st.button("Back", on_click=go, args=(HOME[ss.user["role"]],))
        return
    if forced:
        st.info("An administrator gave you a temporary password. Choose your own before you continue.")
    with st.form("pw", border=False):
        cur = st.text_input("Current password", type="password")
        new = st.text_input("New password", type="password", help="At least 10 characters, different from the current one.")
        again = st.text_input("New password again", type="password")
        save = st.form_submit_button("Save password", type="primary")
    if save:
        problem = None if auth.verify(cur, ss.user["pw"]) is True else "The current password is not correct."
        problem = problem or auth.weak_password(new, cur, ss.user["username"]) or (None if new == again else "The two new passwords are not the same.")
        if problem:
            st.error(problem)
        else:
            storage.set_password(ss.user["id"], auth.hash_password(new), False)
            ss.pw_seen = storage.user_by_id(ss.user["id"])["pw"]  # this session stays signed in; any other session is signed out
            audit("password_changed")
            flash("Password changed.")
            ss.page = HOME[ss.user["role"]]
            st.rerun()
    if not forced:
        st.button("Cancel", on_click=go, args=(HOME[ss.user["role"]],))


def page_unavailable():
    H(ui.PUBLIC_CSS)
    st.title("This page is not available")
    st.write("The link may be wrong, or this airline is not using the service right now.")


# ---------- customer pages ----------
def public_shell(title, sub, points):
    H(ui.PUBLIC_CSS)
    left, right = st.columns([1, 1.08], gap="large")
    with left:
        H(f'<div style="margin-bottom:46px">{ui.brand(product=False, org=ORG["name"])}</div>')
        st.title(title)
        pts = "".join(f'<div style="display:flex;gap:14px;align-items:center;margin:14px 0;color:#E7ECF3;font-weight:600"><span style="width:32px;height:32px;border-radius:50%;background:#fff;color:{ui.DARK};display:flex;align-items:center;justify-content:center;font-weight:800;flex:0 0 32px">{i}</span>{t}</div>' for i, t in enumerate(points, 1))
        H(f'<p style="color:#B9C4D3;font-size:1.15rem;line-height:1.55;max-width:26em;margin-top:18px">{sub}</p><div style="margin-top:28px">{pts}</div>')
        if ss.user:
            st.button(":material/arrow_back: Back to my workspace", on_click=go, args=(HOME[ss.user["role"]],))
    return right


def page_form():
    right = public_shell("Something went wrong? Tell us.",
                         "Describe the problem in your own words. A member of our team reads every complaint.",
                         ["You send your complaint", "A person reads it and approves a reply", "You read the reply here, using your reference"])
    with right, st.container(key="card"):
        if ss.get("sent_ref"):
            H(f'<div style="font-size:2rem;font-weight:800;margin-top:4px">We have your complaint</div>')
            st.success(f"Thank you. Your complaint has been received. Your reference is **{ss.sent_ref}**.")
            st.code(ss.sent_ref, language=None)
            H(ui.stepper(["Received", "Reviewed", "Reply ready"], 1))
            st.caption("Keep this reference, or bookmark the next page. You do not need an account: the reference is how we know it is your complaint.")
            b1, b2 = st.columns(2)
            b1.button("Check progress", type="primary", width="stretch", on_click=lambda: (ss.update(status_ref=ss.sent_ref), go("status")))
            b2.button("Send another", width="stretch", on_click=lambda: ss.update(sent_ref=None))
            return
        st.subheader("Your complaint")
        with st.form("complaint", border=False):
            flight = st.text_input("Flight number (optional)", placeholder="EX 123")
            text = st.text_area("What happened, and when?", height=180, help="At least 10 and at most 1,000 characters.")
            sent = st.form_submit_button("Send complaint", type="primary", width="stretch")
        st.caption(f"{len(text)} of 1,000 characters")
        if sent:
            err = triage.validate(text)
            if not err and (len(flight.strip()) > 12 or not all(ch.isalnum() or ch in " -" for ch in flight.strip())):
                err = "The flight number looks wrong. Use letters and numbers only, for example EX 123, or leave it empty."
            now = time.time()
            mine = [t for t in ss.get("sent_times", []) if now - t < 600]
            if err:
                st.error(err)
            elif len(mine) >= 5 or storage.count_events(ORG["id"], "received", now - 600, role="customer") >= 30:
                st.error("We are receiving a lot of complaints right now. Please wait a few minutes and try again.")  # rate limit
            else:
                ss.sent_times = mine + [now]
                item = _add(text, "Customer form", flight=flight.strip())
                ss.sent_ref = item["ref"]
                st.rerun()
        st.caption("Please don't include card numbers or passwords." + (f" {ORG['name']} is a fictional airline used for this prototype." if ORG["demo"] else ""))
        st.button("Already sent one? Check its progress", on_click=go, args=("status",))
        if not ss.user:
            st.button("Staff sign in", on_click=go, args=("login",))


def _thread(item):
    """The whole conversation as the customer may see it: their messages, and replies a person approved."""
    msgs = storage.messages(ORG["id"], item["id"])
    out = [("customer", item["text"], item["created"])] + [(m["sender"], m["text"], m["ts"]) for m in msgs]
    if item["status"] == "Approved" and item["final_reply"] and not any(m["sender"] == "staff" for m in msgs):
        out.append(("staff", item["final_reply"], item.get("resolved") or item["created"]))  # answered before conversations were kept
    return out


def _follow_up_form(item):
    if (item.get("followups") or 0) >= storage.MAX_FOLLOWUPS:
        st.caption("You have reached the limit of replies on this complaint. If the problem is still not solved, please send a new complaint.")
        return
    st.write("")
    st.subheader("Reply to us")
    with st.form("followup", border=False, clear_on_submit=True):
        text = st.text_area("Your message", height=130, help="At least 10 and at most 1,000 characters.", key="followup_text")
        sent = st.form_submit_button("Send reply", type="primary", width="stretch")
    if sent:
        err = triage.validate(text)
        now = time.time()
        mine = [t for t in ss.get("sent_times", []) if now - t < 600]
        if err:
            st.error(err)
        elif len(mine) >= 5 or storage.count_events(ORG["id"], "follow_up", now - 600, role="customer") >= 30:
            st.error("We are receiving a lot of messages right now. Please wait a few minutes and try again.")
        else:
            lvl, why = triage.urgency("Can't Tell", text)
            if storage.reopen(ORG["id"], item["id"], triage.mask(text), category="High" if lvl == "High" else None, why=why):
                ss.sent_times = mine + [now]
                storage.log(ORG["id"], "customer", "customer", "follow_up", item["ref"], "customer wrote back")
                st.rerun()
            else:
                st.error("This complaint cannot take a reply right now. Please refresh the page.")


def page_status():
    right = public_shell("Check your complaint", "Enter the reference we gave you when you sent your complaint.",
                         ["We have your complaint", "A person reads it", "You see the reply here"])
    if not ss.get("status_ref") and st.query_params.get("ref"):
        ss.status_ref = st.query_params["ref"]  # a bookmarked link opens straight on the complaint
    with right, st.container(key="card"):
        known = storage.get_by_ref(ORG["id"], ss.get("status_ref")) if ss.get("status_ref") else None
        with st.form("status", border=False):
            ref = st.text_input("Reference", placeholder="EX-ABCD2345", key="status_ref")
            look = st.form_submit_button("Refresh status" if known else "Check progress", type="primary", width="stretch")
        if look or ref:
            now = time.time()
            misses = [t for t in ss.get("bad_refs", []) if now - t < 600]
            item = storage.get_by_ref(ORG["id"], ref) if (ref and len(misses) < 10) else None  # only this airline's complaints can be found here
            if ref and len(misses) >= 10:
                st.error("Too many tries. Please wait a few minutes and try again.")
            elif look and not item:
                ss.bad_refs = misses + [now]
                st.error("We could not find that reference. Check it and try again.")
            elif item:
                st.query_params["ref"] = item["ref"]
                cs = triage.customer_status(item)
                H(ui.stepper(["Received", "Reviewed", "Reply ready"], cs["step"]))
                st.subheader(cs["label"])
                st.write(cs["message"])
                for who, text, ts in _thread(item):
                    if who == "customer":
                        H(f'<div class="muted" style="margin:14px 0 4px;font-weight:700">You, {when(ts)}</div><div style="padding:10px 14px;border-radius:14px;background:#EAF1FB">{esc(text).replace(chr(10), "<br>")}</div>')
                    else:
                        H(f'<div class="muted" style="margin:14px 0 6px;font-weight:700">Reply from {esc(ORG["sign_off"])}, {when(ts)}</div><div class="bubble">{esc(text).replace(chr(10), "<br>")}</div>')
                if item["status"] == "Approved":
                    _follow_up_form(item)
                st.caption("Bookmark this page. Its link already contains your reference, so you can come back any time without signing in.")
        st.button("Send a new complaint", on_click=go, args=("form",))


# ---------- agent pages ----------
def list_css(items, selected):
    css = []
    for i in items:
        c, bg, tx = ui.CAT[i["category"]]
        sel = i["id"] == selected
        k = f".st-key-b{i['id']}"
        css.append(f"{k} button{{display:block;text-align:left;border-radius:18px;min-height:88px;height:auto;padding:12px 16px;background:#fff;"
                   f"border:1.5px solid {'#0F1A2B' if sel else '#E3E7EC'};border-left:8px solid {c};"
                   f"{'box-shadow:0 10px 24px rgba(15,26,43,.16);' if sel else ''}}}"
                   f"{k} button > div{{display:block;width:100%;white-space:normal;overflow:visible;text-overflow:clip}}"
                   f"{k} button:hover,{k} button:focus,{k} button:active{{background:#fff;color:#12282A}}"
                   f"{k} button p{{text-align:left;white-space:normal;font-size:14.5px;font-weight:600;line-height:1.4;margin:0}}"
                   f"{k} button p:first-child{{color:{tx};font-weight:800;font-size:12px;letter-spacing:.04em;margin-bottom:4px}}")
    H("<style>" + "".join(css) + "</style>")


def page_queue():
    first = ss.user["name"].split()[0]
    h1, h2 = st.columns([3, 1.2], vertical_alignment="bottom")
    with h1:
        st.title(f"Hello, {first}")
        st.write("Here is what needs you today.")
    with h2:
        H('<div class="live" style="margin-bottom:8px"><i></i>Live queue</div>')
        if ORG["demo"] and st.button(":material/bolt: Simulate 3 new tweets", width="stretch"):  # demo airline only
            _replay(3)
            st.rerun()
        st.toggle("AI drafts (Gemini)", key="use_ai", disabled=not llm.available(),
                  help="Needs GEMINI_API_KEY in the app's secrets. Without it, fixed templates are used.")
    allitems = storage.items(ORG["id"])
    is_lead = ss.user["role"] == auth.LEAD
    waiting = [i for i in allitems if i["status"] == "New"]
    escalated = [i for i in allitems if i["status"] == "Escalated"]
    todo = waiting + (escalated if is_lead else [])  # what this person can act on
    c = {k: sum(1 for i in todo if i["category"] == k) for k in ORDER}
    back = sum(1 for i in todo if i.get("followups") and i["status"] == "New")
    if is_lead:
        stats = [("dark", len(escalated), "Escalated, waiting for you"), ("", len(waiting), "Waiting for an agent"),
                 ("", c["High"], "Need a reply first"), ("", back, "Customers who wrote back")]
    else:
        day = time.time() - 86400
        mine = sum(1 for e in storage.events(ORG["id"], 5000) if e["action"] == "approved" and e["actor_id"] == ss.user["id"] and e["ts"] >= day)
        stats = [("dark", len(waiting), "Complaints waiting"), ("", c["High"], "Need a reply first"),
                 ("", back, "Customers who wrote back"), ("", mine, "Replies you sent, last 24 h")]
    cols = st.columns(4)
    for col, (cls, n, lab) in zip(cols, stats):
        with col:
            H(f'<div class="stat {cls}"><div class="n">{n}</div><div class="l">{lab}</div></div>')
    H('<div style="height:22px"></div>')
    if todo:
        bar = "".join(f"<div style='flex:{c[k]};background:{ui.CAT[k][0]}'></div>" for k in ORDER if c[k])
        leg = "".join(f"<span style='display:inline-flex;align-items:center;gap:6px;margin-right:18px'><span class='dot' style='background:{ui.CAT[k][0]}'></span>{ui.CAT_NAME[k]} {c[k]}</span>" for k in ORDER)
        H(f"<div style='display:flex;gap:3px;height:16px;margin:0 0 8px;border-radius:999px;overflow:hidden'>{bar}</div><div class='muted' style='margin-bottom:18px'>{leg}</div>")
    options = ["All", "High", "Medium", "Low", "Review"] + (["Escalated"] if is_lead else [])
    f = st.segmented_control("Show", options, default="All", key="filter", label_visibility="collapsed") or "All"
    H('<div style="height:14px"></div>')
    new = [i for i in allitems if i["status"] in ("New", "Escalated")]
    if f == "Escalated":
        show = [i for i in new if i["status"] == "Escalated"]  # the team lead's work list
    else:
        show = [i for i in new if f == "All" or i["category"] == f]
    show.sort(key=lambda i: (0 if (is_lead and i["status"] == "Escalated") else 1, ORDER[i["category"]], i["created"]))  # escalations first for the lead (AC1.1, AC1.2)
    if not show:
        st.info("No complaints waiting.")  # AC1.3
        return
    left, right = st.columns([2, 3], gap="large")
    with left:
        list_css(show[:25], ss.selected)
        for i in show[:25]:
            tag = f"{ui.CAT_NAME[i['category']].upper()}  ·  {age(i)}" + ("  ·  ESCALATED" if i["status"] == "Escalated" else "") + ("  ·  FOLLOW-UP" if i.get("followups") and i["status"] == "New" else "")
            if st.button(f"{tag}\n\n{md_esc(i['text'][:110])}", key=f"b{i['id']}", width="stretch"):
                ss.selected = i["id"]
        if len(show) > 25:
            st.caption(f"{len(show) - 25} more below the first 25")
    with right:
        item = next((i for i in allitems if i["id"] == ss.selected), None)
        if not item:
            H('<div class="card" style="text-align:center;padding:60px 24px"><div style="font-size:2.4rem">✈</div><div style="font-weight:800;font-size:1.2rem;margin-top:8px">Pick a complaint</div><div class="muted">You will see the suggested reason, urgency, team and a draft reply.</div></div>')
            return
        detail(item)


def detail(item):
    with st.container(key="detail"):
        status_chip = f'<span class="chip" style="background:#EEF1F5;color:#344054">{item["status"]}</span>'
        H(f'<div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">{ui.chip(item["category"])}{status_chip}<span class="muted">From {esc(item["source"])}, {age(item)} ago · {esc(item["ref"])}{" · Flight " + esc(item["flight"]) if item.get("flight") else ""}</span></div>')
        H(f'<div class="quote">{esc(item["text"])}</div>')
        thread = storage.messages(ORG["id"], item["id"]) if item.get("followups") else []
        if thread:
            H('<div class="muted" style="margin:10px 0 6px;font-weight:700">The conversation so far</div>' + "".join(
                f'<div style="margin:6px 0;padding:10px 14px;border-radius:14px;background:{"#EAF1FB" if m["sender"] == "customer" else "#F3F4F6"}">'
                f'<div class="muted" style="font-size:12.5px">{"Customer" if m["sender"] == "customer" else "Reply from " + esc((storage.user_by_username(m["by"]) or {}).get("name") or m["by"] or "staff")} · {when(m["ts"])}</div>'
                f'<div>{esc(m["text"]).replace(chr(10), "<br>")}</div></div>' for m in thread))
        rkey = f"r{item['id']}" + (f"f{item['followups']}" if item.get("followups") else "")  # a new draft box after each follow-up
        base_draft = triage.followup_template(item, ORG) if item.get("followups") else item["draft"]
        ai = item.get("ai") or {}
        if ai.get("summary"):
            H(f'<div style="margin:2px 0 12px"><span class="chip" style="background:#EEF1F5;color:#344054">AI summary</span> <span class="muted" style="font-size:15px">{esc(ai["summary"])}</span></div>')
        H(ui.stepper(["Received", "Triaged", "Approved"], 2))
        a, b, c = st.columns(3)
        with a:
            H(f'<div class="tile"><div class="k">REASON</div><div class="v">{esc(item["reason_label"])}</div><div class="meter"><div style="width:{item["confidence"]:.0%}"></div></div><div class="muted" style="margin-top:4px">{item["confidence"]:.0%} sure</div></div>')
        with b:
            H(f'<div class="tile"><div class="k">WHY {item["urgency"].upper()} URGENCY</div><div class="v" style="font-size:15px;font-weight:600">{esc(item["urgency_why"])}</div></div>')
        with c:
            H(f'<div class="tile"><div class="k">SUGGESTED TEAM</div><div class="v">{esc(item["team"])}</div><div class="muted" style="margin-top:4px">From the routing rules</div></div>')
        st.write("")
        read = True
        if item["flagged"]:
            read = st.checkbox("I have read this complaint", key=f"read{item['id']}")  # AC3.2
        ai_reply = ai.get("reply")
        if ss.get("use_ai") and llm.available() and item["status"] != "Approved":
            capped = storage.count_events(ORG["id"], "ai_draft", time.time() - 3600) + storage.count_events(ORG["id"], "ai_draft_failed", time.time() - 3600) >= 60
            if capped:
                st.caption("This airline has used its AI drafts for this hour. Templates are used until it resets.")
            if st.button(":material/auto_awesome: " + ("Write again with AI" if ai else "Summarise and draft with AI"), key=f"ai{item['id']}", disabled=capped) and not capped:
                try:
                    with st.spinner("Asking Gemini..."):
                        last_customer = next((m["text"] for m in reversed(thread) if m["sender"] == "customer"), None)
                        ask = item["text"] if not last_customer else f"{item['text']}\n\nThe customer has now written back: {last_customer}"
                        res = llm.assist(ask[:1500], item["team"] if not item["flagged"] else triage.DEFAULT_TEAM, ORG)
                    storage.update(ORG["id"], item["id"], ai=res)
                    audit("ai_draft", item["ref"], "AI summary and draft written" if res["reply"] else "AI draft rejected by safety checks")
                    if res["reply"]:
                        ss[rkey] = res["reply"]
                    else:
                        ss[rkey] = base_draft
                        st.warning("The AI draft broke a safety rule, so the template is shown instead.")
                    st.rerun()
                except llm.LLMError as e:
                    audit("ai_draft_failed", item["ref"], str(e)[:120])
                    st.warning(f"The AI draft is unavailable ({e}). The template is shown instead.")
        source = "Drafted by AI" if ai_reply else "Template"
        start_text = ai_reply or base_draft if item["status"] != "Approved" else item["final_reply"]
        reply = st.text_area("Draft reply", value=start_text or base_draft, height=170, key=rkey, max_chars=1500)
        H(f'<span class="chip" style="background:#EEF1F5;color:#344054">{"✨ " if source == "Drafted by AI" else ""}{source}{", edited" if reply.strip() != (ai_reply or base_draft).strip() else ""}</span>')
        problems = [w for w in triage.BLOCKED_WORDS if w in reply.lower()]
        signed = ORG["name"] in reply
        checks = [("No promise of a refund, compensation or rebooking" if not problems else f"Remove: {', '.join(problems)}", not problems),
                  (f"Signed as {ORG['name']}" if signed else f"Sign as {ORG['name']}", signed), ("Handle masked", True)]
        H("".join(f'<span class="check {"" if ok else "bad"}">{"✓" if ok else "!"} {esc(t)}</span>' for t, ok in checks))
        is_lead = ss.user["role"] == "Team lead"
        escalated = item["status"] == "Escalated"
        if item["status"] == "Approved":  # e.g. someone else approved it while this screen was open
            done = next((x for x in storage.events(ORG["id"], ref=item["ref"]) if x["action"] == "approved"), None)
            st.info(f"Already approved by {done['actor']} at {when(done['ts'])}." if done else "Already approved.")
        if item.get("note") and not escalated:
            st.info(f"Team lead's note: {item['note']}")
        if escalated:
            who_ev = next((x for x in storage.events(ORG["id"], ref=item["ref"]) if x["action"] == "escalated"), None)
            by = f"{who_ev['actor']}: {who_ev['detail'] or 'no reason given'}" if who_ev else "no reason recorded"
            if is_lead:
                st.warning(f"Escalated by {by}")
            else:
                st.warning(f"Escalated to the team lead ({by}). They will approve it or send it back to the queue with a note.")
        can_decide = is_lead or not escalated  # only the lead decides an escalated complaint
        ok = read and not problems and signed and item["status"] != "Approved" and can_decide
        b1, _ = st.columns([1.2, 2.4])
        edited = reply.strip() != (ai_reply or base_draft).strip()
        if b1.button(":material/check: Approve reply", type="primary", disabled=not ok, key=f"a{item['id']}", width="stretch") and ok:  # `ok` re-checked on the server
            if storage.update_if(ORG["id"], item["id"], item["status"], final_reply=reply, status="Approved",
                                 resolved=item.get("resolved") or time.time(), approved_by=ss.user["username"]):  # resolved keeps the time of the FIRST reply
                storage.add_message(ORG["id"], item["id"], "staff", reply, ss.user["username"])
                audit("approved", item["ref"], f"{source}{', edited by the agent' if edited else ', sent as drafted'}" + (", reply to a follow-up" if item.get("followups") else ""))
            else:  # someone else changed it while this screen was open
                flash("Someone else already handled that complaint, so your change was not saved.")
            ss.selected = None
            st.rerun()
        if is_lead and escalated:
            note = st.text_input("Note for the agent (optional)", key=f"note{item['id']}", placeholder="For example: refund approved, reply as drafted", max_chars=300)
            if st.button(":material/undo: Return to queue", key=f"ret{item['id']}"):
                if storage.update_if(ORG["id"], item["id"], "Escalated", status="New", note=note.strip() or None):
                    audit("returned", item["ref"], note.strip() or "no note")
                else:
                    flash("Someone else already handled that complaint, so your change was not saved.")
                ss.selected = None
                st.rerun()
        elif not is_lead and not escalated and item["status"] == "New":
            why = st.text_input("Why are you escalating this? (required)", key=f"why{item['id']}", placeholder="For example: customer asks for compensation I cannot approve", max_chars=200)
            if st.button(":material/flag: Escalate to team lead", key=f"e{item['id']}", disabled=len(why.strip()) < 5) and len(why.strip()) >= 5:
                if storage.update_if(ORG["id"], item["id"], "New", status="Escalated", note=None):
                    audit("escalated", item["ref"], why.strip())
                else:
                    flash("Someone else already handled that complaint, so your change was not saved.")
                    ss.selected = None
                st.rerun()
        st.caption("Approving makes the reply visible to the customer on their status page. Nothing else is sent.")
        with st.expander("History of this complaint"):
            for x in storage.events(ORG["id"], ref=item["ref"]):
                st.write(f"**{when(x['ts'])}**  ·  {x['actor']}  ·  {ACTION_LABELS.get(x['action'], x['action'])}" + (f"  ·  {x['detail']}" if x["detail"] else ""))


# ---------- routing ----------
if PUBLIC and not ss.user:
    ss.page = VIEW
if ss.get("flash"):
    st.warning(ss.pop("flash"))

if PUBLIC:
    if not ORG or not ORG["active"]:
        page_unavailable()
    else:
        {"form": page_form, "status": page_status}[VIEW]()
elif not ss.user:
    page_login()
else:
    role = ss.user["role"]
    if ss.page in ("form", "status"):  # a signed-in person opened a customer page
        ss.page = HOME[role]
    p = "password" if ss.user["must_change"] else (ss.page if ss.page in ALLOWED[role] else HOME[role])
    ss.page = p
    sidebar()
    {"queue": page_queue, "insights": lambda: insights.page_insights(STAFF_ORG), "password": page_password,
     "dashboard": lambda: admin_pages.page_dashboard(STAFF_ORG), "staff": lambda: admin_pages.page_staff(STAFF_ORG),
     "activity": lambda: admin_pages.page_log(STAFF_ORG), "platlog": lambda: admin_pages.page_log(None),
     "overview": admin_pages.page_overview, "airlines": admin_pages.page_airlines,
     "allusers": admin_pages.page_users, "system": admin_pages.page_system}[p]()
