"""Pages for the two admin levels.
Platform admin: adds airlines, oversees every user and the whole system.
Airline admin: sees their own airline's dashboard, manages its staff and reads its log.
Every page checks the role again, and every query is limited to the airline it is about."""
import json, os, platform, re, sys, time

import pandas as pd
import streamlit as st

import auth, insights, llm, mailer, storage, ui
import seed
from common import ACTION_LABELS, airline_links, audit, base_url, clean_name, csv_safe, esc, flash, valid_email, when
from ui import H

ss = st.session_state
MAX_USERS = 50  # active accounts per airline
MAX_NEW_PER_HOUR = 20  # accounts one airline can create per hour
MAX_EMAILS_PER_HOUR, MAX_EMAILS_PER_DAY = 30, 200  # per airline, and across the whole platform
USERNAME = re.compile(r"^[a-z0-9._-]{3,30}$")


def _need(*roles):
    if not ss.user or ss.user["role"] not in roles:
        st.error("You do not have access to this page.")
        return False
    return True


def _reveal():
    """After an account is created or reset: either 'emailed', or the one-time password to hand over yourself."""
    r = ss.get("reveal")
    if not r:
        return
    with st.container(border=True):
        st.success(r["title"])
        if r.get("emailed"):
            st.write(f"The sign-in link, username and temporary password were emailed to **{r['email']}**. The password is not shown here. If it does not arrive, use Reset password to send a new one.")
        else:
            if r.get("email"):
                st.warning("The email was not sent" + (f" ({r['error']})." if r.get("error") else ".") + " Give the person these details yourself.")
            st.write(f"Username: **{r['username']}**")
            st.write("Temporary password (shown once, so copy it now):")
            st.code(r["password"], language=None)
            for label, url in (r.get("links") or {}).items():
                st.write(f"{label}:")
                st.code(url, language=None)
            if r.get("mailto"):
                st.link_button("Open a ready-made email", r["mailto"])
            st.caption("They must choose their own password when they first sign in.")
        if st.button("Done", key="reveal_done"):
            ss.reveal = None
            st.rerun()


def _may_email(org):
    """Email is never sent for the shared demo airline, and is capped so the system cannot be used to spam strangers."""
    if not mailer.configured() or (org and org["demo"]):
        return False
    now = time.time()
    if org and storage.count_events(org["id"], "credentials_emailed", now - 3600) >= MAX_EMAILS_PER_HOUR:
        return False
    return storage.count_events_all("credentials_emailed", now - 86400) < MAX_EMAILS_PER_DAY


def _issue(user, temp, org, title, reset=False):
    """Email the sign-in details if email is allowed; otherwise keep them for the admin to hand over once."""
    link = airline_links(org)["Staff sign-in"] if org else base_url()
    airline = org["name"] if org else "Tower"
    f = mailer.reset_notice if reset else mailer.welcome
    args = (user["name"], airline, user["username"], temp, link) if reset else (user["name"], airline, user["role"], user["username"], temp, link)
    subject, body, html = f(*args)
    ok, why = mailer.send(user["email"], subject, body, html) if (user.get("email") and _may_email(org)) else (False, "")
    if ok:
        audit("credentials_emailed", "", f"{user['name']} ({user['username']})", airline_id=user["airline_id"])
    ss.reveal = {"title": title, "username": user["username"], "password": None if ok else temp, "email": user.get("email"), "emailed": ok, "error": why,
                 "links": airline_links(org) if org else {"Sign-in link": link},
                 "mailto": None if ok or not user.get("email") else mailer.mailto(user["email"], subject, body)}


def _new_user(airline_id, name, username, role, email, org=None, platform=False):
    """Create an account with a temporary password. Returns an error message or None."""
    username = username.strip().lower()
    name = clean_name(name)
    email = (email or "").strip()
    if role not in auth.STAFF_ROLES and not (platform and role == auth.PLATFORM_ADMIN and ss.user["role"] == auth.PLATFORM_ADMIN):
        return "Choose a role from the list."
    if not name:
        return "Enter the person's name using letters, numbers, spaces and . ' - only."
    if not valid_email(email):
        return "Enter a valid email address. The sign-in details are sent there."
    if not platform and sum(1 for x in storage.users(airline_id) if x["active"]) >= MAX_USERS:
        return f"This airline already has {MAX_USERS} active users. Deactivate someone first."
    if not platform and storage.count_events(airline_id, "user_added", time.time() - 3600) >= MAX_NEW_PER_HOUR:
        return f"This airline has added {MAX_NEW_PER_HOUR} people in the last hour. Please wait before adding more."
    if not USERNAME.match(username):
        return "Usernames are 3 to 30 characters: lowercase letters, numbers, dots, dashes or underscores."
    temp = auth.temp_password()
    u = storage.add_user(airline_id, username, name, role, auth.hash_password(temp), must_change=True, created_by=ss.user["username"], email=email)
    if not u:
        return "That username is already taken. Choose another."
    audit("user_added", "", f"{name} ({username}) as {role}", airline_id=airline_id)
    _issue(u, temp, org or (storage.airline(airline_id) if airline_id else None), f"Account created for {name}")
    return None


def _details_form(u, key):
    """Edit one person's name and email. Their username and sign-in stay the same. Returns True if something changed."""
    name = st.text_input("Name", value=u["name"], key=f"{key}nm{u['id']}")
    mail = st.text_input("Email", value=u.get("email") or "", key=f"{key}em{u['id']}")
    if not st.button("Save name and email", key=f"{key}eb{u['id']}"):
        return False
    new_name, new_mail = clean_name(name), mail.strip()
    if not new_name:
        st.error("Enter a name using letters, numbers, spaces and . ' & - only.")
    elif new_mail != (u.get("email") or "") and not valid_email(new_mail):
        st.error("Enter a valid email address.")
    elif new_name == u["name"] and new_mail == (u.get("email") or ""):
        st.info("Nothing to save: no changes were made.")
    else:
        if new_name != u["name"]:
            storage.set_user_name(u["id"], new_name)
            audit("name_changed", "", f"{u['name']} to {new_name} ({u['username']})", airline_id=u["airline_id"])
        if new_mail != (u.get("email") or ""):
            storage.set_email(u["id"], new_mail)
            audit("email_changed", "", f"{new_name} ({u['username']})", airline_id=u["airline_id"])
        return True
    return False


def _change_role(u, key):
    """Change a person's role or email. A role change takes effect on their next click."""
    me = ss.user
    if u["id"] == me["id"] or u["role"] not in auth.STAFF_ROLES or (u["created_by"] == "setup" and me["role"] != auth.PLATFORM_ADMIN):
        return False
    with st.expander("Change name, role or email"):
        new = st.selectbox("Role", auth.STAFF_ROLES, index=auth.STAFF_ROLES.index(u["role"]), key=f"{key}rs{u['id']}")
        if st.button("Save role", key=f"{key}rb{u['id']}") and new != u["role"] and new in auth.STAFF_ROLES:
            others = [x for x in storage.users(u["airline_id"]) if x["active"] and x["role"] == auth.ORG_ADMIN and x["id"] != u["id"]]
            if u["role"] == auth.ORG_ADMIN and not others:
                flash("That is the only active airline admin. Add another first so nobody is locked out.")
            else:
                storage.set_role(u["id"], new)
                audit("role_changed", "", f"{u['name']} ({u['username']}): {u['role']} to {new}", airline_id=u["airline_id"])
                return True
        if _details_form(u, key):
            return True
    return False


def _state(u):
    if not u["active"]:
        return ":red[Deactivated]"
    if auth.temp_expired(u):
        return ":orange[Temporary password expired. Reset it]"
    return "Active, not signed in yet" if u["must_change"] and u["created_by"] != "setup" else "Active"


def _user_actions(u, key_prefix, org_id_filter=None):
    """Deactivate / reactivate / reset password for one user. Returns True if something changed."""
    me = ss.user
    c1, c2 = st.columns(2)
    changed = False
    if u["id"] == me["id"]:
        c1.caption("This is you")
        return False
    if u["created_by"] == "setup" and me["role"] != auth.PLATFORM_ADMIN:
        c1.caption("Shared demo account: only the platform admin can change it")
        return False
    if u["active"]:
        if c1.button("Deactivate", key=f"{key_prefix}d{u['id']}"):
            actives = [x for x in storage.users(u["airline_id"]) if x["active"] and x["role"] == u["role"]] if u["airline_id"] else \
                      [x for x in storage.users() if x["active"] and x["role"] == auth.PLATFORM_ADMIN]
            if u["role"] in (auth.ORG_ADMIN, auth.PLATFORM_ADMIN) and len(actives) <= 1:
                flash(f"{u['name']} is the only active {u['role'].lower()}. Add another first so nobody is locked out.")
            else:
                storage.set_user_active(u["id"], False)
                audit("user_deactivated", "", f"{u['name']} ({u['username']})", airline_id=u["airline_id"])
            changed = True
    else:
        if c1.button("Reactivate", key=f"{key_prefix}r{u['id']}"):
            storage.set_user_active(u["id"], True)
            audit("user_reactivated", "", f"{u['name']} ({u['username']})", airline_id=u["airline_id"])
            changed = True
    if c2.button("Reset password", key=f"{key_prefix}p{u['id']}"):
        temp = auth.temp_password()
        storage.set_password(u["id"], auth.hash_password(temp), True)
        audit("password_reset", "", f"{u['name']} ({u['username']})", airline_id=u["airline_id"])
        _issue(u, temp, storage.airline(u["airline_id"]) if u["airline_id"] else None, f"New temporary password for {u['name']}", reset=True)
        changed = True
    return changed


# ======================= AIRLINE ADMIN =======================
def page_dashboard(org):
    """The airline administrator's view: the big picture over months (not the day-to-day queue, which is the team lead's Insights)."""
    if not _need(auth.ORG_ADMIN):
        return
    st.title(f"{org['name']} dashboard")
    st.write("The big picture: how many complaints come in, how well they are answered, and who is on your team.")
    items, staff = storage.items(org["id"]), storage.users(org["id"])
    now = time.time()
    total = len(items)
    done = [i for i in items if i["status"] == "Approved"]
    this_m, last_m = (insights.month_key(now), insights.month_key(now - 31 * 86400))
    n_this = sum(1 for i in items if insights.month_key(i["created"]) == this_m)
    n_last = sum(1 for i in items if insights.month_key(i["created"]) == last_m)
    trend = "" if not n_last else f" ({(n_this - n_last) / n_last:+.0%} vs last month)"
    wrote = sum(1 for i in items if i.get("followups"))
    active = [u for u in staff if u["active"]]
    esc_n = sum(1 for e in storage.events(org["id"], 20000) if e["action"] == "escalated")
    insights.cards([(total, "Complaints received", True), (n_this, f"Received this month{trend}", False),
                    (f"{len(done) / total:.0%}" if total else "n/a", f"Replied to ({len(done)} of {total})", False),
                    (f"{wrote / len(done):.0%}" if done else "n/a", "Customers who wrote back after a reply", False)])
    insights.cards([(insights.hours(insights.first_reply_hours(items)), "Average time to first reply", False),
                    (f"{esc_n / total:.0%}" if total else "n/a", "Escalated to a team lead", False),
                    (f"{sum(1 for i in items if i['category'] == 'High') / total:.0%}" if total else "n/a", "Of complaints are High urgency", False),
                    (len(active), f"Active users ({len(staff) - len(active)} deactivated)", False)])
    if not items:
        st.info("No complaints yet. They appear here as customers use your complaint form.")
    else:
        months = insights.last_months(12)
        recv, res = dict.fromkeys(months, 0), dict.fromkeys(months, 0)
        hrs = {m: [] for m in months}
        for i in items:
            m = insights.month_key(i["created"])
            if m in recv:
                recv[m] += 1
                res[m] += i["status"] == "Approved"
                if i["status"] == "Approved" and i.get("resolved"):
                    hrs[m].append((i["resolved"] - i["created"]) / 3600)
        left, right = st.columns([1.5, 1], gap="large")
        with left:
            with insights.box("Complaints received by month", "Last 12 months, UTC. Dark = received, light = replied to."):
                st.bar_chart(pd.DataFrame({"Received": recv, "Replied to": res}), color=[insights.INK, insights.SOFT], stack=False, height=280)
        with right:
            with insights.box("Reasons for complaints", "All complaints received."):
                H(insights.bars(list(pd.Series([i["reason_label"] for i in items]).value_counts().items())))
        st.write("")
        left, right = st.columns([1.5, 1], gap="large")
        with left:
            with insights.box("Average time to first reply, by month", "Hours from the complaint arriving to the first approved reply. Lower is better."):
                st.line_chart(pd.DataFrame({"Hours": {m: (sum(v) / len(v) if v else None) for m, v in hrs.items()}}), color=[insights.INK], height=240)
        with right:
            with insights.box("When complaints arrive", "By day of the week. Use it to plan who is on shift."):
                days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                cnt = pd.Series([days[time.gmtime(i["created"]).tm_wday] for i in items]).value_counts()
                H(insights.bars([(d, int(cnt.get(d, 0))) for d in days]))
        st.write("")
        a, b = st.columns(2, gap="large")
        with a:
            with insights.box("By urgency", "How serious complaints are when they arrive."):
                ser = pd.Series([i["urgency"] for i in items]).value_counts()
                H(insights.bars([(k, int(ser.get(k, 0))) for k in ("High", "Medium", "Low")]))
        with b:
            with insights.box("By team that should handle it", "Based on the routing rules."):
                H(insights.bars(list(pd.Series([i["team"] for i in items]).value_counts().items())))
    st.write("")
    left, right = st.columns(2, gap="large")
    with left:
        with insights.box("Your team", "Active accounts, and sign-ins in the last 7 days. Manage people under Staff."):
            week = now - 7 * 86400
            logins = pd.Series([e["actor"] for e in storage.events(org["id"], 20000) if e["action"] == "signed_in" and e["ts"] >= week]).value_counts()
            rows = [{"Name": u["name"], "Role": u["role"], "Sign-ins, 7 days": int(logins.get(u["name"], 0)), "Status": "Active" if u["active"] else "Deactivated"} for u in staff]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    with right:
        with insights.box("Your links", "Give the customer links to your customers. Staff use the sign-in link."):
            for label, url in airline_links(org).items():
                st.write(label)
                st.code(url, language=None)


def page_staff(org):
    if not _need(auth.ORG_ADMIN):
        return
    st.title("Staff")
    st.write(f"People who can sign in to {org['name']}. Deactivating someone takes effect straight away.")
    _reveal()
    with st.expander("Add a person", expanded=not storage.users(org["id"])[1:]):
        with st.form("adduser", clear_on_submit=True, border=False):
            c1, c2 = st.columns(2)
            name = c1.text_input("Name")
            email = c2.text_input("Email", help="Their sign-in link, username and temporary password are sent here.")
            c3, c4 = st.columns(2)
            username = c3.text_input("Username", help="Lowercase, no spaces. For example thandi.m")
            role = c4.selectbox("Role", auth.STAFF_ROLES, help="Support agent works the queue. Team lead also decides escalations and sees Insights. Airline admin manages staff and sees the dashboard.")
            go = st.form_submit_button("Create account", type="primary")
        if not mailer.configured():
            st.caption("Email is not set up on this system yet, so the details are shown once after you create the account.")
        if go:
            err = _new_user(org["id"], name, username, role, email, org=org)
            if err:
                st.error(err)
            else:
                st.rerun()
    people = storage.users(org["id"])
    st.caption(f"{sum(1 for u in people if u['active'])} active, {sum(1 for u in people if not u['active'])} deactivated")
    for u in people:
        with st.container(border=True):
            a, b, c, d = st.columns([2, 1.5, 1, 2.4], vertical_alignment="center")
            a.write(f"**{u['name']}**  \n{u['username']}" + (f"  \n{u['email']}" if u.get("email") else ""))
            b.write(u["role"])
            c.write(_state(u))
            with d:
                if _user_actions(u, "o"):
                    st.rerun()
            if _change_role(u, "o"):
                st.rerun()


# ---------- activity log (an airline's own, or the whole platform's when org is None) ----------
def page_log(org):
    if org is None:
        if not _need(auth.PLATFORM_ADMIN):
            return
    elif not _need(auth.ORG_ADMIN, auth.LEAD):
        return
    st.title("Platform log" if org is None else "Activity log")
    st.write("Who did what, newest first. Times are UTC. The log never records complaint text, passwords or keys.")
    ev = storage.events(None if org is None else org["id"], 3000)
    if not ev:
        st.info("Nothing recorded yet.")
        return
    names = {a["id"]: a["name"] for a in storage.airlines()}
    df = pd.DataFrame(ev)
    df["When"] = df.ts.map(when)
    df["What"] = df.action.map(lambda x: ACTION_LABELS.get(x, x))
    df["Airline"] = [names.get(a if pd.notna(a) else b, "Platform") if (pd.notna(a) or pd.notna(b)) else "Platform" for a, b in zip(df.airline_id, df.about_id)]
    f1, f2, f3, f4 = st.columns(4) if org is None else (*st.columns(3), None)
    what = f1.multiselect("What", sorted(df.What.unique()))
    who_ = f2.multiselect("Who", sorted(df.actor.unique()))
    ref = f3.text_input("Complaint reference", placeholder="EX-ABCD2345").strip().upper()
    air = f4.multiselect("Airline", sorted(df.Airline.unique())) if f4 is not None else []
    if what:
        df = df[df.What.isin(what)]
    if who_:
        df = df[df.actor.isin(who_)]
    if ref:
        df = df[df.ref == ref]
    if air:
        df = df[df.Airline.isin(air)]
    cols = ["When", "Airline", "Who", "Role", "What", "Complaint", "Detail"] if org is None else ["When", "Who", "Role", "What", "Complaint", "Detail"]
    view = df.rename(columns={"actor": "Who", "role": "Role", "ref": "Complaint", "detail": "Detail"})[cols]
    st.caption(f"{len(view)} entries")
    st.dataframe(view, hide_index=True, width="stretch")
    st.download_button("Download as CSV", view.map(csv_safe).to_csv(index=False), file_name="activity-log.csv", mime="text/csv")


# ======================= PLATFORM ADMIN =======================
def _default_password_in_use():
    return seed.default_admin_in_use()


def page_overview():
    if not _need(auth.PLATFORM_ADMIN):
        return
    st.title("Platform overview")
    st.write("Every airline on Tower, at a glance. Complaint contents stay private to each airline: you see only counts.")
    if _default_password_in_use():
        st.warning("A platform admin account is still using the published demo password. Change it with the key icon in the sidebar before sharing this app.")
    als, users = storage.airlines(), storage.users()
    now = time.time()
    all_items = {a["id"]: storage.items(a["id"]) for a in als}
    total = sum(len(v) for v in all_items.values())
    month = sum(1 for v in all_items.values() for i in v if insights.month_key(i["created"]) == insights.month_key(now))
    fails = sum(1 for e in storage.events(None, 5000) if e["action"] == "sign_in_failed" and e["ts"] >= now - 86400)
    insights.cards([(sum(1 for a in als if a["active"]), f"Active airlines ({len(als)} in total)", True),
                    (sum(1 for u in users if u["active"]), f"Active users ({len(users)} in total)", False),
                    (total, "Complaints on the platform", False), (month, "Received this month", False),
                    (fails, "Failed sign-ins, last 24 h", False)])
    rows = []
    for a in als:
        v = all_items[a["id"]]
        done = sum(1 for i in v if i["status"] == "Approved")
        us = [u for u in users if u["airline_id"] == a["id"]]
        last = max((e["ts"] for e in storage.events(a["id"], 300) if e["action"] == "signed_in"), default=None)
        rows.append({"Airline": a["name"], "Status": "Active" if a["active"] else "Deactivated", "Users": sum(1 for u in us if u["active"]),
                     "Complaints": len(v), "Replied to": f"{done / len(v):.0%}" if v else "n/a", "Open now": sum(1 for i in v if i["status"] in ("New", "Escalated")),
                     "Last staff sign-in": when(last) if last else "never"})
    with insights.box("Airlines", "Open now = waiting for a reply. An airline with open complaints and no recent sign-in may need a call."):
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.write("")
    left, right = st.columns([1.5, 1], gap="large")
    with left:
        with insights.box("Complaints per month, by airline", "Last 6 months, UTC."):
            months = insights.last_months(6)
            data = {a["name"]: {m: 0 for m in months} for a in als}
            for a in als:
                for i in all_items[a["id"]]:
                    m = insights.month_key(i["created"])
                    if m in data[a["name"]]:
                        data[a["name"]][m] += 1
            st.bar_chart(pd.DataFrame(data), color=(["#0F1A2B", "#8FA3C4", "#4F7CAC", "#D99100", "#C2331F", "#6B7C8C"] * 10)[:len(data)], height=260)
    with right:
        with insights.box("Users per airline", "Active accounts."):
            H(insights.bars([(a["name"], sum(1 for u in users if u["airline_id"] == a["id"] and u["active"])) for a in als]))


def page_airlines():
    if not _need(auth.PLATFORM_ADMIN):
        return
    st.title("Airlines")
    st.write("Add an airline and its first administrator. Each airline gets its own links, and cannot see any other airline's data.")
    _reveal()
    with st.expander("Add an airline", expanded=len(storage.airlines()) <= 1):
        with st.form("addairline", clear_on_submit=True, border=False):
            c1, c2 = st.columns(2)
            name = c1.text_input("Airline name")
            sign_off = c2.text_input("Sign-off on replies (optional)", placeholder="Defaults to: <name> Customer Care")
            st.write("**First administrator for this airline**")
            d1, d2 = st.columns(2)
            admin_name = d1.text_input("Their name")
            admin_email = d2.text_input("Their email", help="Their sign-in link, username and temporary password are sent here.")
            admin_user = st.text_input("Their username", help="Lowercase, no spaces. For example lerato.n")
            go = st.form_submit_button("Add airline", type="primary")
        if not mailer.configured():
            st.caption("Email is not set up on this system yet, so the details are shown once after you add the airline.")
        if go:
            if not clean_name(name):
                st.error("Enter the airline's name using letters, numbers, spaces and . ' & - only.")
            elif storage.airline_by_name(name):
                st.error("An airline with that name already exists.")
            elif sign_off.strip() and (len(sign_off.strip()) > 60 or not clean_name(sign_off)):
                st.error("The sign-off can be up to 60 characters, letters, numbers, spaces and . ' & - only.")
            elif storage.user_by_username(admin_user):
                st.error("That username is already taken. Choose another.")
            elif not valid_email(admin_email):
                st.error("Enter a valid email address for the administrator. The sign-in details are sent there.")
            elif not USERNAME.match(admin_user.strip().lower()) or not clean_name(admin_name):
                st.error("Enter the administrator's name and a username (3 to 30 characters: lowercase letters, numbers, dots, dashes or underscores).")
            else:
                al = storage.add_airline(clean_name(name), clean_name(sign_off) if sign_off.strip() else None)
                audit("airline_added", "", al["name"], airline_id=al["id"])
                err = _new_user(al["id"], admin_name, admin_user, auth.ORG_ADMIN, admin_email, org=al)
                if err:
                    st.error(err)
                else:
                    st.rerun()
    for al in storage.airlines():
        users, items = storage.users(al["id"]), storage.items(al["id"])
        with st.container(border=True):
            a, b = st.columns([3, 1.4], vertical_alignment="center")
            a.markdown(f"**{al['name']}**  {'(demo)' if al['demo'] else ''}  \n{'Active' if al['active'] else ':red[Deactivated]'} · "
                       f"{sum(1 for u in users if u['active'])} active users · {len(items)} complaints · {sum(1 for i in items if i['status'] == 'Approved')} resolved")
            with b:
                if al["active"]:
                    if st.button("Deactivate airline", key=f"ad{al['id']}"):
                        ss.confirm_off = al["id"]
                    if ss.get("confirm_off") == al["id"]:
                        st.warning("Its staff are signed out at once, and its customer links stop working. Data is kept.")
                        if st.button("Yes, deactivate", key=f"ady{al['id']}", type="primary"):
                            storage.set_airline_active(al["id"], False)
                            audit("airline_deactivated", "", al["name"], airline_id=al["id"])
                            ss.confirm_off = None
                            st.rerun()
                elif st.button("Reactivate airline", key=f"ar{al['id']}"):
                    storage.set_airline_active(al["id"], True)
                    audit("airline_reactivated", "", al["name"], airline_id=al["id"])
                    st.rerun()
            with st.expander("Edit airline name and sign-off"):
                if al["demo"]:
                    st.caption("The shared demo airline keeps its name so the demo stays the same for everyone.")
                else:
                    st.caption("Links keep working after a rename. Replies already sent keep the sign-off they were sent with.")
                    n1 = st.text_input("Airline name", value=al["name"], key=f"an{al['id']}")
                    n2 = st.text_input("Sign-off on replies", value=al["sign_off"], key=f"as{al['id']}")
                    if st.button("Save airline", key=f"asv{al['id']}"):
                        nm, so = clean_name(n1), clean_name(n2)
                        other = storage.airline_by_name(n1)
                        if not nm:
                            st.error("Enter the airline's name using letters, numbers, spaces and . ' & - only.")
                        elif not so or len(so) > 60:
                            st.error("The sign-off can be up to 60 characters, letters, numbers, spaces and . ' & - only.")
                        elif other and other["id"] != al["id"]:
                            st.error("An airline with that name already exists.")
                        elif nm == al["name"] and so == al["sign_off"]:
                            st.info("Nothing to save: no changes were made.")
                        else:
                            storage.update_airline(al["id"], nm, so)
                            audit("airline_edited", "", f"{al['name']} to {nm}" if nm != al["name"] else nm, airline_id=al["id"])
                            st.rerun()
            for u in (x for x in users if x["role"] == auth.ORG_ADMIN):
                with st.expander(f"Edit administrator: {u['name']} ({u['username']})"):
                    if _details_form(u, "a"):
                        st.rerun()
            with st.expander("Links and administrators"):
                for label, url in airline_links(al).items():
                    st.write(label)
                    st.code(url, language=None)
                st.write("Airline administrators: " + (", ".join(f"{u['name']} ({u['username']}{'' if u['active'] else ', deactivated'})" for u in users if u["role"] == auth.ORG_ADMIN) or "none"))


def page_users():
    if not _need(auth.PLATFORM_ADMIN):
        return
    st.title("All users")
    st.write("Everyone on the platform, across all airlines.")
    _reveal()
    with st.expander("Add another platform admin", expanded=False):
        st.caption("A second platform admin means you are never locked out if one person is away or loses access.")
        with st.form("addplat", clear_on_submit=True, border=False):
            p1, p2 = st.columns(2)
            pname = p1.text_input("Name")
            pmail = p2.text_input("Email")
            puser = st.text_input("Username", help="Lowercase, no spaces. For example nomsa.d")
            pgo = st.form_submit_button("Create platform admin", type="primary")
        if pgo:
            err = _new_user(None, pname, puser, auth.PLATFORM_ADMIN, pmail, platform=True)
            if err:
                st.error(err)
            else:
                st.rerun()
    names = {a["id"]: a["name"] for a in storage.airlines()}
    users = storage.users()
    f1, f2, f3 = st.columns(3)
    air = f1.multiselect("Airline", ["Platform"] + sorted(names.values()))
    role = f2.multiselect("Role", sorted({u["role"] for u in users}))
    status = f3.selectbox("Status", ["All", "Active", "Deactivated"])
    shown = [u for u in users if (not air or names.get(u["airline_id"], "Platform") in air) and (not role or u["role"] in role)
             and (status == "All" or u["active"] == (status == "Active"))]
    st.caption(f"{len(shown)} of {len(users)} users")
    for u in shown:
        with st.container(border=True):
            a, b, c, d = st.columns([2, 1.6, 1.4, 2.4], vertical_alignment="center")
            a.write(f"**{u['name']}**  \n{u['username']}" + (f"  \n{u['email']}" if u.get("email") else ""))
            b.write(f"{names.get(u['airline_id'], 'Platform')}  \n{u['role']}")
            c.write(_state(u))
            with d:
                if _user_actions(u, "p"):
                    st.rerun()
            with st.expander("Edit name and email"):
                if _details_form(u, "p"):
                    st.rerun()


def page_system():
    if not _need(auth.PLATFORM_ADMIN):
        return
    st.title("System")
    st.write("Health checks and where to look when something goes wrong.")
    if _default_password_in_use():
        st.warning("A platform admin account is still using the published demo password. Change it with the key icon in the sidebar.")
    left, right = st.columns(2, gap="large")
    with left:
        with st.container(border=True):
            st.subheader("AI drafts (Gemini)")
            if llm.available():
                st.write(f"Key found. Model: **{llm._secret('GEMINI_MODEL', llm.DEFAULT_MODEL)}**")
                if st.button("Test the connection"):
                    try:
                        with st.spinner("Asking Gemini..."):
                            r = llm.assist("My bag did not arrive after my flight and nobody has answered my calls.", "Baggage Services")
                        st.success("Gemini answered." if r["reply"] else "Gemini answered, but its reply failed the safety checks.")
                    except llm.LLMError as e:
                        st.error(f"Gemini is unavailable: {e}")
            else:
                st.write("No key set, so replies use the fixed templates. Add GEMINI_API_KEY in the app's secrets to switch AI drafts on.")
        with st.container(border=True):
            st.subheader("Software")
            st.write(f"Python {sys.version.split()[0]} · Streamlit {st.__version__} · {platform.system()}")
            st.write(f"Triage model: {'found' if os.path.exists(os.path.join(os.path.dirname(__file__), 'model', 'reason_model.joblib')) else 'MISSING'}")
            st.write(f"Email: {'set up' if mailer.configured() else 'not set up (sign-in details are shown once instead of emailed)'}")
        m = json.load(open(os.path.join(os.path.dirname(__file__), "model", "metrics.json")))
        with st.container(border=True):
            st.subheader("How well the triage model works")
            st.write(f"The model picks the right complaint reason {m['accuracy']:.0%} of the time on tweets it had not seen. When it is at least {int(m['threshold'] * 100)}% sure it is right {m['thresholds']['0.5']['accuracy']:.0%} of the time, "
                     f"and below that the complaint is flagged for a person. Guessing the most common reason scores {m['baseline']:.0%}.")
            st.caption(f"Kaggle Twitter US Airline Sentiment (2015, English). Trained on {m['n_train']:,} tweets, tested on {m['n_test']:,}. Urgency and team come from rules, not data. This is about the tool, so it is shown here and not in the airlines' own Insights.")
    with right:
        with st.container(border=True):
            st.subheader("Database")
            p = storage.db_path()
            size = os.path.getsize(p) / 1e6 if os.path.exists(p) else 0
            st.write(f"`{p}` · {size:.2f} MB")
            st.write(f"{len(storage.airlines())} airlines · {len(storage.users())} users · {storage.count()} complaints")
            st.caption("On the free hosted version this file is erased whenever the app restarts. A production setup needs a hosted database.")
        with st.container(border=True):
            st.subheader("Recent problems")
            probs = [e for e in storage.events(None, 500) if e["action"] in ("sign_in_failed", "ai_draft_failed")][:10]
            if not probs:
                st.write("Nothing recent.")
            names = {a["id"]: a["name"] for a in storage.airlines()}
            for e in probs:
                st.write(f"{when(e['ts'])} · {names.get(e['airline_id'], 'Platform')} · {ACTION_LABELS[e['action']]} · {e['actor']} {e['detail']}")
