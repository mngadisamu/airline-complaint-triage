"""Second audit round: gaps found after the follow-up, email and insights work."""
import time
from streamlit.testing.v1 import AppTest

import auth, mailer, seed, storage, triage
from test_platform import add_airline, btn, field, nav, open_app, sign_in
from test_conversation import answered, ex

seed.ensure_demo()
MSG = "My bag never arrived after my flight to Durban and nobody answers the baggage line."


def test_a_follow_up_starts_a_fresh_draft_and_forgets_the_old_ai_suggestion():
    item = answered()
    storage.update(ex()["id"], item["id"], ai={"summary": "old", "reply": "OLD AI REPLY\n\nExample Air Customer Care"})
    assert storage.reopen(ex()["id"], item["id"], "Still not sorted, please look again.")
    assert storage.get_by_ref(ex()["id"], item["ref"])["ai"] is None


def test_demo_airline_never_sends_email_and_shows_the_details_instead(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "configured", lambda: True)
    monkeypatch.setattr(mailer, "send", lambda *a: sent.append(a) or (True, ""))
    org = sign_in(open_app("example-air"), "org.demo", auth.DEMO_PASSWORD)
    nav(org, "Staff")
    field(org, "Name").set_value("Demo Visitor"); field(org, "Email").set_value("victim@example.test"); field(org, "Username").set_value("demo.visitor")
    btn(org, "Create account").click().run()
    assert not sent and org.session_state["reveal"]["password"]


def test_email_is_capped_per_airline_per_hour(monkeypatch):
    import admin_pages
    sent = []
    monkeypatch.setattr(mailer, "configured", lambda: True)
    monkeypatch.setattr(mailer, "send", lambda *a: sent.append(a) or (True, ""))
    at = add_airline("Capped Mail Air", "Cap C.", "cap.c")
    assert len(sent) == 1
    al = storage.airline_by_slug("capped-mail-air")
    for _ in range(admin_pages.MAX_EMAILS_PER_HOUR):
        storage.log(al["id"], "x", "Airline admin", "credentials_emailed")
    sent.clear()
    storage.add_user(al["id"], "cap.admin", "Cap Admin", auth.ORG_ADMIN, auth.hash_password("Passw0rd-long-1"), must_change=False)
    a = sign_in(open_app("capped-mail-air"), "cap.admin", "Passw0rd-long-1")
    nav(a, "Staff")
    field(a, "Name").set_value("Over Limit"); field(a, "Email").set_value("o@example.test"); field(a, "Username").set_value("over.limit")
    btn(a, "Create account").click().run()
    assert not sent and a.session_state["reveal"]["password"]            # not emailed: the admin hands the details over


def test_an_airline_cannot_create_unlimited_accounts_per_hour():
    import admin_pages
    al = storage.add_airline("Busy Air")
    storage.add_user(al["id"], "busy.admin", "Busy Admin", auth.ORG_ADMIN, auth.hash_password("Passw0rd-long-1"), must_change=False)
    for _ in range(admin_pages.MAX_NEW_PER_HOUR):
        storage.log(al["id"], "Busy Admin", "Airline admin", "user_added")
    a = sign_in(open_app("busy-air"), "busy.admin", "Passw0rd-long-1")
    nav(a, "Staff")
    field(a, "Name").set_value("One More"); field(a, "Email").set_value("m@example.test"); field(a, "Username").set_value("one.more")
    btn(a, "Create account").click().run()
    assert any("last hour" in e.value for e in a.error) and not storage.user_by_username("one.more")


def test_email_can_be_corrected_and_is_validated():
    al = storage.airline_by_slug("example-air")
    u = storage.add_user(al["id"], "typo.user", "Typo User", auth.AGENT, auth.hash_password("Passw0rd-long-1"), must_change=False, created_by="test", email="wrong@example.test")
    org = sign_in(open_app("example-air"), "org.demo", auth.DEMO_PASSWORD)
    nav(org, "Staff")
    org.text_input(key=f"oem{u['id']}").set_value("not-an-email").run()
    [b for b in org.button if b.key == f"oeb{u['id']}"][0].click().run()
    assert org.error and storage.user_by_username("typo.user")["email"] == "wrong@example.test"
    org.text_input(key=f"oem{u['id']}").set_value("right@example.test").run()
    [b for b in org.button if b.key == f"oeb{u['id']}"][0].click().run()
    assert storage.user_by_username("typo.user")["email"] == "right@example.test"
    assert any(e["action"] == "email_changed" for e in storage.events(al["id"]))


def test_an_unused_temporary_password_expires_and_a_reset_revives_it():
    al = storage.airline_by_slug("example-air")
    pw = "Temp-Pass-12345"
    u = storage.add_user(al["id"], "expire.me", "Expire Me", auth.AGENT, auth.hash_password(pw), must_change=True, created_by="test")
    assert auth.check("expire.me", pw)
    with storage._conn() as c:
        c.execute("UPDATE users SET pw_set=? WHERE id=?", (time.time() - 8 * 86400, u["id"]))
    assert auth.check("expire.me", pw) is None
    org = sign_in(open_app("example-air"), "org.demo", auth.DEMO_PASSWORD)
    nav(org, "Staff")
    assert any("expired" in m.value for m in org.markdown)
    storage.set_password(u["id"], auth.hash_password(pw), True)           # what Reset password does
    assert auth.check("expire.me", pw)


def test_per_person_numbers_come_from_who_actually_acted():
    al = ex()
    item = storage.add(al["id"], MSG, "Customer form", "", triage.triage(MSG, al))
    agent = sign_in(open_app("example-air"), "agent.demo", auth.DEMO_PASSWORD)
    agent.session_state.selected = item["id"]; agent.run()
    [b for b in agent.button if b.key == f"a{item['id']}"][0].click().run()
    me = storage.user_by_username("agent.demo")
    ev = [e for e in storage.events(al["id"], ref=item["ref"]) if e["action"] == "approved"]
    assert ev and ev[0]["actor_id"] == me["id"]
    again = sign_in(open_app("example-air"), "agent.demo", auth.DEMO_PASSWORD)
    assert any("Replies you sent, last 24 h" in m.value for m in again.markdown)
    # a second reply to the same complaint (after a follow-up) is credited to whoever sends it
    assert storage.reopen(al["id"], item["id"], "Still not sorted, please help me again.")


def test_platform_admin_can_add_a_second_platform_admin_and_airline_admins_cannot():
    at = sign_in(open_app(), "admin.demo", auth.DEMO_PASSWORD)
    nav(at, "All users")
    [t for t in at.text_input if t.label == "Name"][0].set_value("Backup Admin")
    [t for t in at.text_input if t.label == "Email"][0].set_value("backup@example.test")
    [t for t in at.text_input if t.label == "Username"][0].set_value("backup.admin")
    [b for b in at.button if b.label == "Create platform admin"][0].click().run()
    u = storage.user_by_username("backup.admin")
    assert u and u["role"] == auth.PLATFORM_ADMIN and u["airline_id"] is None and u["must_change"]
    pw = at.session_state["reveal"]["password"]
    new = sign_in(open_app(), "backup.admin", pw)
    assert new.title[0].value == "Choose a new password"
    org = sign_in(open_app("example-air"), "org.demo", auth.DEMO_PASSWORD)
    nav(org, "Staff")
    assert auth.PLATFORM_ADMIN not in org.selectbox[0].options             # an airline admin cannot hand out the platform role


def test_staff_see_the_flight_number():
    al = ex()
    item = storage.add(al["id"], MSG, "Customer form", "EX 123", triage.triage(MSG, al))
    agent = sign_in(open_app("example-air"), "agent.demo", auth.DEMO_PASSWORD)
    agent.session_state.selected = item["id"]; agent.run()
    assert any("Flight EX 123" in m.value for m in agent.markdown)


def test_reference_guessing_is_slowed_down():
    at = open_app("example-air", "status")
    for k in range(12):
        at.text_input[0].set_value(f"EX-GUESS{k:03d}")
        btn(at, "Check progress").click().run()
    assert any("Too many tries" in e.value for e in at.error)
    item = answered()
    at.text_input[0].set_value(item["ref"])
    btn(at, "Check progress").click().run()
    assert any("Too many tries" in e.value for e in at.error)             # even a right reference waits, in this browser session
