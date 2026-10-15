"""Customer follow-ups, the team lead's queue and Insights, scoped logs, and emailing sign-in details."""
import smtplib, time
from streamlit.testing.v1 import AppTest

import auth, mailer, seed, storage, triage
from test_platform import add_airline, btn, field, nav, open_app, sign_in

seed.ensure_demo()
MSG = "My bag never arrived after my flight to Durban and nobody answers the baggage line."


def ex():
    return storage.airline_by_slug("example-air")


def answered(text=MSG, reply="Thank you for contacting us. We are sorry about your bag.\n\nExample Air Customer Care"):
    al = ex()
    item = storage.add(al["id"], text, "Customer form", "", triage.triage(text, al))
    storage.update(al["id"], item["id"], status="Approved", final_reply=reply, resolved=time.time(), approved_by="agent.demo")
    return storage.get_by_ref(al["id"], item["ref"])


def status_page(item):
    return open_app("example-air", "status", ref=item["ref"])


# ---------------- customer follow-up ----------------
def test_customer_can_reply_after_an_answer_and_it_returns_to_the_queue():
    item = answered()
    at = status_page(item)
    assert any("Reply from Example Air" in m.value for m in at.markdown)
    at.text_area(key="followup_text").set_value("Thank you, but my bag still has not arrived. Please look again.")
    btn(at, "Send reply").click().run()
    got = storage.get_by_ref(ex()["id"], item["ref"])
    assert got["status"] == "New" and got["followups"] == 1
    assert any("Follow-up received" in str(x.value) for x in at.subheader)
    assert not [b for b in at.button if b.label == "Send reply"]           # cannot reply twice before a person answers
    assert [e for e in storage.events(ex()["id"], ref=item["ref"]) if e["action"] == "follow_up"]
    thread = storage.messages(ex()["id"], item["id"])
    assert [m["sender"] for m in thread] == ["staff", "customer"]          # the first reply was kept in the thread


def test_agent_sees_the_conversation_and_the_customer_sees_the_new_reply():
    item = answered()
    st_ = status_page(item)
    st_.text_area(key="followup_text").set_value("Still waiting for my bag, please help me with it today.")
    btn(st_, "Send reply").click().run()
    agent = sign_in(open_app("example-air"), "agent.demo", auth.DEMO_PASSWORD)
    key = [b for b in agent.button if (b.key or "").startswith("b") and "FOLLOW-UP" in b.label and "Still waiting" not in b.label]
    big = storage.get_by_ref(ex()["id"], item["ref"])
    agent.session_state.selected = big["id"]; agent.run()
    assert any("The conversation so far" in m.value for m in agent.markdown)
    assert any("Still waiting for my bag" in m.value for m in agent.markdown)
    box = agent.text_area(key=f"r{big['id']}f1")
    assert "Thank you for getting back to us" in box.value                 # a follow-up template, not the first reply
    box.set_value("We are sorry your bag is still missing. We have asked the baggage team to look into it again.\n\nExample Air Customer Care").run()
    [b for b in agent.button if b.key == f"a{big['id']}"][0].click().run()
    after = storage.get_by_ref(ex()["id"], item["ref"])
    assert after["status"] == "Approved" and after["approved_by"] == "agent.demo"
    assert after["resolved"] == big["resolved"]                            # first-reply time is not overwritten
    cust = status_page(item)
    assert len([m for m in cust.markdown if "Reply from Example Air" in m.value]) == 2
    assert [b for b in cust.button if b.label == "Send reply"]             # and they may answer again


def test_follow_up_is_limited_validated_and_airline_scoped():
    item = answered()
    al = ex()
    assert storage.reopen(al["id"] + 999, item["id"], "hello there friend", None) is False      # another airline cannot reopen it
    for _ in range(storage.MAX_FOLLOWUPS):
        assert storage.reopen(al["id"], item["id"], "Still not sorted out, please help.")
        storage.update(al["id"], item["id"], status="Approved", final_reply="Reply.\n\nExample Air Customer Care")
    assert storage.reopen(al["id"], item["id"], "One more please.") is False
    at = status_page(item)
    assert not [b for b in at.button if b.label == "Send reply"]
    short = answered()
    at = status_page(short)
    at.text_area(key="followup_text").set_value("ok")
    btn(at, "Send reply").click().run()
    assert at.error and storage.get_by_ref(al["id"], short["ref"])["status"] == "Approved"


def test_unanswered_complaints_show_no_reply_box_and_urgent_follow_up_raises_urgency():
    al = ex()
    new = storage.add(al["id"], MSG, "Customer form", "", triage.triage(MSG, al))
    assert not [b for b in status_page(new).button if b.label == "Send reply"]
    item = answered()
    assert storage.reopen(al["id"], item["id"], "My flight leaves tomorrow and I am stuck at the airport", category="High", why="urgent")
    assert storage.get_by_ref(al["id"], item["ref"])["category"] == "High"


# ---------------- team lead queue and insights ----------------
def test_lead_queue_counts_and_lists_escalated_complaints_first():
    al = ex()
    item = storage.add(al["id"], "My flight was cancelled and nobody will tell me what to do next.", "Customer form", "", triage.triage("My flight was cancelled", al))
    storage.update(al["id"], item["id"], status="Escalated")
    lead = sign_in(open_app("example-air"), "lead.demo", auth.DEMO_PASSWORD)
    nav(lead, "Queue")
    n_esc = sum(1 for i in storage.items(al["id"]) if i["status"] == "Escalated")
    assert any("Escalated, waiting for you" in m.value and f">{n_esc}<" in m.value for m in lead.markdown)
    first = [b for b in lead.button if (b.key or "")[:1] == "b" and (b.key or "")[1:].isdigit()][0]
    assert "ESCALATED" in first.label                                       # escalations are on top for the lead
    agent = sign_in(open_app("example-air"), "agent.demo", auth.DEMO_PASSWORD)
    assert not any("Escalated, waiting for you" in m.value for m in agent.markdown)


def test_insights_are_about_the_airline_and_for_leads_only():
    lead = sign_in(open_app("example-air"), "lead.demo", auth.DEMO_PASSWORD)
    nav(lead, "Insights")
    text = " ".join(m.value for m in lead.markdown)
    for phrase in ("Complaints in the last 14 days", "How long open complaints have waited", "Time to first reply, by urgency", "Your agents, last 7 days", "Customers who wrote back"):
        assert phrase in text, phrase
    assert "Accuracy on unseen tweets" not in text and "(F1)" not in text      # how the tool works is not the lead's concern
    assert not lead.exception


# ---------------- logs are scoped ----------------
def test_airline_log_never_shows_platform_admin_actions_but_platform_log_does():
    at = add_airline("Quiet Skies", "Quin Q.", "quin.q")
    al = storage.airline_by_slug("quiet-skies")
    assert not [e for e in storage.events(al["id"]) if e["role"] == "Platform admin"]
    plat = [e for e in storage.events(None) if e["action"] == "airline_added" and e["about_id"] == al["id"]]
    assert plat and plat[0]["airline_id"] is None
    admin = sign_in(open_app("quiet-skies"), "quin.q", "irrelevant")  # wrong password: still signed out
    assert admin.title[0].value == "Welcome back"
    # a legacy row that was tagged with the airline is still hidden from it
    storage.log(al["id"], "Nomsa D.", "Platform admin", "password_reset", "", "old row")
    assert not [e for e in storage.events(al["id"]) if e["role"] == "Platform admin"]
    nav(plat_page := at, "Platform log")
    assert plat_page.dataframe


# ---------------- email ----------------
def test_credentials_are_emailed_when_email_is_set_up(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "configured", lambda: True)
    monkeypatch.setattr(mailer, "send", lambda to, subject, body: sent.append((to, subject, body)) or (True, ""))
    at = add_airline("Mail Test Air", "Mia M.", "mia.m")
    assert len(sent) == 1
    to, subject, body = sent[0]
    assert to == "mia.m@example.test" and "Mail Test Air" in subject
    rev = at.session_state["reveal"]
    assert rev["emailed"] and rev["password"] is None                       # the password is not shown on screen when it was emailed
    u = storage.user_by_username("mia.m")
    temp = [l for l in body.splitlines() if l.startswith("Temporary password:")][0].split(": ")[1]
    assert auth.verify(temp, u["pw"]) and "?airline=mail-test-air" in body and "mia.m" in body
    assert any(e["action"] == "credentials_emailed" for e in storage.events(None))
    assert not any(temp in str(e) for e in storage.events(None))             # the password never reaches the log


def test_if_email_fails_the_admin_still_gets_the_details_once(monkeypatch):
    monkeypatch.setattr(mailer, "configured", lambda: True)
    monkeypatch.setattr(mailer, "send", lambda *a: (False, "SMTPAuthenticationError"))
    at = add_airline("Mail Fail Air", "Fay F.", "fay.mf")
    rev = at.session_state["reveal"]
    assert not rev["emailed"] and rev["password"] and rev["mailto"].startswith("mailto:fay.mf%40example.test")
    assert any("not sent" in w.value for w in at.warning)


def test_email_is_required_and_checked():
    at = platform_page()
    field(at, "Airline name").set_value("No Mail Air")
    field(at, "Their name").set_value("Nia N."); field(at, "Their username").set_value("nia.n"); field(at, "Their email").set_value("not-an-email")
    btn(at, "Add airline").click().run()
    assert any("valid email" in e.value for e in at.error) and not storage.airline_by_name("No Mail Air")


def platform_page():
    at = sign_in(open_app(), "admin.demo", auth.DEMO_PASSWORD)
    nav(at, "Airlines")
    return at


def test_mailer_talks_smtp_without_leaking_the_password(monkeypatch):
    calls = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=0): calls["host"], calls["port"] = host, port
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self, context=None): calls["tls"] = True
        def login(self, u, p): calls["login"] = (u, p)
        def send_message(self, m): calls["msg"] = m
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    for k, v in (("SMTP_HOST", "smtp.example.test"), ("SMTP_FROM", "Tower <no-reply@example.test>"), ("SMTP_USER", "u"), ("SMTP_PASSWORD", "secret-app-password")):
        monkeypatch.setenv(k, v)
    ok, why = mailer.send("a@example.test", "Hello", "Body")
    assert ok and calls["port"] == 587 and calls["tls"] and calls["login"] == ("u", "secret-app-password") and calls["msg"]["To"] == "a@example.test"

    class Boom(FakeSMTP):
        def login(self, u, p): raise smtplib.SMTPAuthenticationError(535, b"bad credentials secret-app-password")
    monkeypatch.setattr(smtplib, "SMTP", Boom)
    ok, why = mailer.send("a@example.test", "Hello", "Body")
    assert not ok and why == "SMTPAuthenticationError" and "secret-app-password" not in why
