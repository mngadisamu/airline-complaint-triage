from streamlit.testing.v1 import AppTest
import auth

import seed
seed.ensure_demo()
def AID():
    return storage.airline_by_slug("example-air")["id"]

def fresh():
    at = AppTest.from_file("../app.py", default_timeout=60)
    at.query_params["airline"] = "example-air"
    at.run()
    return at

def login(at, user, pw):
    at.text_input[0].set_value(user)
    at.text_input[1].set_value(pw)
    [b for b in at.button if b.label == 'Sign in'][0].click().run() if False else None
    [b for b in at.button if b.label == "Sign in"][0].click().run()

def test_signed_out_sees_login_only():
    at = fresh()
    assert at.title[0].value == "Welcome back"

def test_wrong_password_and_lockout():
    at = fresh()
    for _ in range(5):
        at.text_input[0].set_value("agent.demo"); at.text_input[1].set_value("nope")
        [b for b in at.button if b.label == 'Sign in'][0].click().run()
    assert any("not correct" in e.value for e in at.error) or at.warning
    assert any("Wait" in w.value for w in at.warning)
    at.text_input[0].set_value("agent.demo"); at.text_input[1].set_value(auth.DEMO_PASSWORD)
    [b for b in at.button if b.label == 'Sign in'][0].click().run()
    assert at.title[0].value == "Welcome back"  # still locked

def test_agent_has_no_insights_and_lead_does():
    at = fresh()
    at.text_input[0].set_value("agent.demo"); at.text_input[1].set_value(auth.DEMO_PASSWORD)
    [b for b in at.button if b.label == 'Sign in'][0].click().run()
    assert "Thandi" in at.title[0].value
    assert not any("Insights" in b.label for b in at.sidebar.button)
    at2 = fresh()
    at2.text_input[0].set_value("lead.demo"); at2.text_input[1].set_value(auth.DEMO_PASSWORD)
    [b for b in at2.button if b.label == 'Sign in'][0].click().run()
    assert at2.title[0].value == "Insights"  # the lead starts on Insights
    assert any("Insights" in b.label for b in at2.sidebar.button)
    [b for b in at2.sidebar.button if "Queue" in b.label][0].click().run()
    assert "Sipho" in at2.title[0].value
    labels = lambda a: [o.content for o in (a.get("segmented_control") or a.get("button_group"))[0].proto.options]
    assert "Escalated" in labels(at2)  # lead-only work list
    assert "Escalated" not in labels(at)

def test_form_validation_and_submit():
    at = fresh()
    [b for b in at.button if "Send a complaint" in b.label][0].click().run()
    assert at.title[0].value == "Something went wrong? Tell us."
    at.text_area[0].set_value("short")
    [b for b in at.button if b.label == "Send complaint"][0].click().run()
    assert at.error
    at.text_area[0].set_value("My bag never arrived after my flight to Durban and nobody answers the baggage line.")
    [b for b in at.button if b.label == "Send complaint"][0].click().run()
    assert at.success


import re, storage, triage

def test_public_form_link_shows_form_only():
    at = AppTest.from_file("../app.py", default_timeout=60)
    at.query_params["airline"] = "example-air"; at.query_params["view"] = "form"
    at.run()
    assert at.title[0].value == "Something went wrong? Tell us."
    assert not at.sidebar.button

def test_reference_and_status_flow():
    at = AppTest.from_file("../app.py", default_timeout=60)
    at.query_params["airline"] = "example-air"; at.query_params["view"] = "form"
    at.run()
    at.text_area[0].set_value("My flight to Cape Town was cancelled and nobody at the desk will help us.")
    [b for b in at.button if b.label == "Send complaint"][0].click().run()
    ref = re.search(r"EX-[A-Z0-9]{8}", at.success[0].value).group(0)
    item = storage.get_by_ref(AID(), ref)
    assert item and item["status"] == "New"
    # customer sees progress but no reply yet
    cs = triage.customer_status(item)
    assert cs["label"] == "Received" and cs["reply"] is None
    # after a person approves, the customer sees the reply
    storage.update(AID(), item["id"], final_reply="Hello, sorry about that.\n\nExample Air Customer Care", status="Approved")
    cs = triage.customer_status(storage.get_by_ref(AID(), ref.lower()))
    assert cs["label"] == "Replied" and "Example Air" in cs["reply"]
    # status page finds it, and rejects a wrong reference
    at2 = AppTest.from_file("../app.py", default_timeout=60)
    at2.query_params["airline"] = "example-air"; at2.query_params["view"] = "status"
    at2.run()
    at2.text_input[0].set_value("EX-WRONG000")
    [b for b in at2.button if b.label == "Check progress"][0].click().run()
    assert at2.error
    at2.text_input[0].set_value(ref)
    [b for b in at2.button if b.label == "Check progress"][0].click().run()
    assert any("Reply from Example Air" in m.value for m in at2.markdown)

def test_persistence_across_sessions():
    n = storage.count(AID())
    storage.add(AID(), "persist me please", "Customer form", "", triage.triage("persist me please"))
    assert storage.count(AID()) == n + 1


def _pick(at):
    """Open the first complaint that is new and not flagged for a manual read (the DB is shared between tests)."""
    cands = [b for b in at.button if b.key and b.key.startswith("b") and b.key[1:].isdigit()
             and "ESCALATED" not in b.label and "NEEDS REVIEW" not in b.label.upper()]
    cands[0].click().run()
    return int(cands[0].key[1:])


def _escalate(at, item_id, reason):
    at.text_input(key=f"why{item_id}").set_value(reason).run()
    [b for b in at.button if b.key == f"e{item_id}"][0].click().run()


def _by_label(at, text):
    return [b for b in at.button if text in b.label]


def test_escalation_agent_to_lead_and_back_with_note():
    import storage
    # the agent escalates
    at = fresh(); login(at, "agent.demo", auth.DEMO_PASSWORD)
    item_id = _pick(at)
    assert _by_label(at, "Escalate to team lead") and not _by_label(at, "Return to queue")
    _escalate(at, item_id, "Customer wants compensation I cannot approve")
    assert [i for i in storage.items(AID()) if i["id"] == item_id][0]["status"] == "Escalated"
    # the agent can no longer decide it
    _pick_id = [b for b in at.button if b.key == f"b{item_id}"][0]
    _pick_id.click().run()
    assert not _by_label(at, "Escalate to team lead")
    assert [b for b in at.button if b.key == f"a{item_id}"][0].disabled
    assert any("Escalated to the team lead" in w.value for w in at.warning)
    # the lead sees it, has no Escalate button, and can return it with a note
    at2 = fresh(); login(at2, "lead.demo", auth.DEMO_PASSWORD)
    [b for b in at2.sidebar.button if "Queue" in b.label][0].click().run()
    assert not _by_label(at2, "Escalate to team lead")
    [b for b in at2.button if b.key == f"b{item_id}"][0].click().run()
    assert _by_label(at2, "Return to queue")
    at2.text_input(key=f"note{item_id}").set_value("Refund approved, reply as drafted").run()
    _by_label(at2, "Return to queue")[0].click().run()
    got = [i for i in storage.items(AID()) if i["id"] == item_id][0]
    assert got["status"] == "New" and got["note"] == "Refund approved, reply as drafted"
    # the agent sees the note
    at3 = fresh(); login(at3, "agent.demo", auth.DEMO_PASSWORD)
    [b for b in at3.button if b.key == f"b{item_id}"][0].click().run()
    assert any("Refund approved" in i.value for i in at3.info)


def test_lead_can_approve_an_escalated_complaint():
    import storage
    at = fresh(); login(at, "agent.demo", auth.DEMO_PASSWORD)
    item_id = _pick(at)
    _escalate(at, item_id, "Needs a decision on a refund")
    at2 = fresh(); login(at2, "lead.demo", auth.DEMO_PASSWORD)
    [b for b in at2.sidebar.button if "Queue" in b.label][0].click().run()
    [b for b in at2.button if b.key == f"b{item_id}"][0].click().run()
    ap = [b for b in at2.button if b.key == f"a{item_id}"][0]
    assert not ap.disabled
    ap.click().run()
    assert [i for i in storage.items(AID()) if i["id"] == item_id][0]["status"] == "Approved"


def test_status_link_with_reference_opens_the_complaint_without_sign_in():
    import storage, triage
    item = storage.add(AID(), "My bag never arrived after my flight to Durban.", "Complaint form", "", triage.triage("My bag never arrived after my flight to Durban."))
    at = AppTest.from_file("../app.py", default_timeout=60)
    at.query_params["airline"] = "example-air"; at.query_params["view"] = "status"
    at.query_params["ref"] = item["ref"]
    at.run()
    assert any(item["ref"] == t.value or "We have your complaint" in t.value for t in at.markdown) or any("We have your complaint" in m.value for m in at.markdown)
    assert [b for b in at.button if "Refresh status" in b.label]  # no longer a second "Check progress" once it is showing
    assert not any("could not find" in e.value for e in at.error)


def test_escalation_needs_a_reason_and_the_lead_sees_who_and_why():
    at = fresh(); login(at, "agent.demo", auth.DEMO_PASSWORD)
    item_id = _pick(at)
    assert [b for b in at.button if b.key == f"e{item_id}"][0].disabled  # no reason yet
    at.text_input(key=f"why{item_id}").set_value("abc").run()
    assert [b for b in at.button if b.key == f"e{item_id}"][0].disabled  # too short
    _escalate(at, item_id, "Customer asks for compensation")
    at2 = fresh(); login(at2, "lead.demo", auth.DEMO_PASSWORD)
    [b for b in at2.sidebar.button if "Queue" in b.label][0].click().run()
    [b for b in at2.button if b.key == f"b{item_id}"][0].click().run()
    assert any("Thandi M." in w.value and "Customer asks for compensation" in w.value for w in at2.warning)


def test_activity_log_records_who_did_what():
    import storage
    at = fresh(); login(at, "agent.demo", auth.DEMO_PASSWORD)
    item_id = _pick(at)
    ref = [i for i in storage.items(AID()) if i["id"] == item_id][0]["ref"]
    _escalate(at, item_id, "Needs the lead")
    at2 = fresh(); login(at2, "lead.demo", auth.DEMO_PASSWORD)
    [b for b in at2.sidebar.button if "Queue" in b.label][0].click().run()
    [b for b in at2.button if b.key == f"b{item_id}"][0].click().run()
    at2.text_input(key=f"note{item_id}").set_value("Go ahead").run()
    [b for b in at2.button if b.key == f"ret{item_id}"][0].click().run()
    seen = {(e["actor"], e["action"]) for e in storage.events(AID(), ref=ref)}
    assert ("Thandi M.", "escalated") in seen and ("Sipho K.", "returned") in seen
    allseen = {(e["actor"], e["action"]) for e in storage.events(AID())}
    assert ("Thandi M.", "signed_in") in allseen and ("Sipho K.", "signed_in") in allseen
    # the lead can open the log page; the agent has no such page
    [b for b in at2.sidebar.button if "Activity log" in b.label][0].click().run()
    assert at2.title[0].value == "Activity log" and at2.dataframe
    assert not any("Activity log" in b.label for b in at.sidebar.button)


def test_failed_sign_in_is_logged_without_the_password():
    import storage
    at = fresh(); login(at, "agent.demo", "wrong-password-123")
    ev = [e for e in storage.events(AID()) if e["action"] == "sign_in_failed"]
    assert ev and ev[0]["actor"] == "agent.demo"
    assert not any("wrong-password-123" in str(e) for e in storage.events(AID()))
    at2 = fresh(); login(at2, "someone.else", "x")
    assert [e for e in storage.events(AID()) if e["action"] == "sign_in_failed"][0]["actor"] == "unknown user"


def test_second_agent_cannot_overwrite_an_already_handled_complaint():
    import storage
    first = fresh(); login(first, "agent.demo", auth.DEMO_PASSWORD)
    item_id = _pick(first)                      # agent 1 has the complaint open
    second = fresh(); login(second, "agent.demo", auth.DEMO_PASSWORD)
    second.get("button")  # second session opens the same complaint and approves it
    [b for b in second.button if b.key == f"b{item_id}"][0].click().run()
    second.text_area(key=f"r{item_id}").set_value("Hello, thank you for your message. We are looking into it.\n\nExample Air Customer Care").run()
    [b for b in second.button if b.key == f"a{item_id}"][0].click().run()
    saved = [i for i in storage.items(AID()) if i["id"] == item_id][0]
    assert saved["status"] == "Approved"
    winner = saved["final_reply"]
    [b for b in first.button if b.key == f"a{item_id}"][0].click().run()   # agent 1 clicks late
    after = [i for i in storage.items(AID()) if i["id"] == item_id][0]
    assert after["final_reply"] == winner                                  # not overwritten
    assert any("Already approved by" in i.value for i in first.info)  # told who got there first
    assert len([e for e in storage.events(AID(), ref=saved["ref"]) if e["action"] == "approved"]) == 1


def test_public_form_is_rate_limited():
    import time, storage
    at = AppTest.from_file("../app.py", default_timeout=60)
    at.query_params["airline"] = "example-air"; at.query_params["view"] = "form"
    at.session_state["sent_times"] = [time.time()] * 5       # this visitor already sent five
    at.run()
    at.text_area[0].set_value("My bag never arrived after my flight to Durban and nobody answers the baggage line.")
    [b for b in at.button if b.label == "Send complaint"][0].click().run()
    assert any("receiving a lot" in e.value for e in at.error)
    # and a global cap, so many different visitors cannot flood the queue either
    for _ in range(30):
        storage.log(AID(), "customer", "customer", "received", "EX-TEST", "via Customer form")
    at2 = AppTest.from_file("../app.py", default_timeout=60)
    at2.query_params["airline"] = "example-air"; at2.query_params["view"] = "form"
    at2.run()
    at2.text_area[0].set_value("My bag never arrived after my flight to Durban and nobody answers the baggage line.")
    [b for b in at2.button if b.label == "Send complaint"][0].click().run()
    assert any("receiving a lot" in e.value for e in at2.error)
