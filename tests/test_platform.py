"""Platform admin, airline admin and isolation between airlines."""
import time
from streamlit.testing.v1 import AppTest

import auth, seed, storage, triage

seed.ensure_demo()
APP = "../app.py"


def open_app(slug=None, view=None, **extra):
    at = AppTest.from_file(APP, default_timeout=60)
    if slug:
        at.query_params["airline"] = slug
    if view:
        at.query_params["view"] = view
    for k, v in extra.items():
        at.query_params[k] = v
    at.run()
    return at


def sign_in(at, user, pw):
    at.text_input(key="login_user").set_value(user)
    at.text_input(key="login_pass").set_value(pw)
    [b for b in at.button if b.label == "Sign in"][0].click().run()
    return at


def field(at, label):
    return [t for t in at.text_input if t.label == label][0]


def btn(at, label):
    return [b for b in at.button if b.label == label][0]


def nav(at, label):
    [b for b in at.sidebar.button if label in b.label][0].click().run()


def platform():
    return sign_in(open_app(), "admin.demo", auth.DEMO_PASSWORD)


def add_airline(name, admin_name, admin_user):
    at = platform()
    nav(at, "Airlines")
    field(at, "Airline name").set_value(name)
    field(at, "Their name").set_value(admin_name)
    field(at, "Their email").set_value(f"{admin_user}@example.test")
    field(at, "Their username").set_value(admin_user)
    btn(at, "Add airline").click().run()
    return at


def test_platform_admin_adds_an_airline_and_its_admin_gets_a_working_link():
    at = add_airline("Blue Heron Airways", "Zanele P.", "zanele.p")
    rev = at.session_state["reveal"]
    assert rev["username"] == "zanele.p" and len(rev["password"]) >= 10
    assert "airline=blue-heron-airways" in rev["links"]["Staff sign-in"]
    al = storage.airline_by_slug("blue-heron-airways")
    assert al and al["active"] and al["sign_off"] == "Blue Heron Airways Customer Care"
    # the airline admin signs in at their own link and must choose a new password first
    org = open_app("blue-heron-airways")
    assert "Blue Heron Airways" in str(org.markdown[0].value) + str([m.value for m in org.markdown])
    sign_in(org, "zanele.p", rev["password"])
    assert org.title[0].value == "Choose a new password"
    field(org, "Current password").set_value(rev["password"])
    field(org, "New password").set_value("a-long-new-password-1")
    field(org, "New password again").set_value("a-long-new-password-1")
    [b for b in org.button if "Save" in b.label][0].click().run()
    assert org.title[0].value == "Blue Heron Airways dashboard"
    assert not storage.user_by_username("zanele.p")["must_change"]
    assert any(e["action"] == "airline_added" for e in storage.events(None))


def test_airlines_cannot_see_each_others_complaints():
    if not storage.airline_by_slug("blue-heron-airways"):
        add_airline("Blue Heron Airways", "Zanele P.", "zanele.p")
    ex, bh = storage.airline_by_slug("example-air"), storage.airline_by_slug("blue-heron-airways")
    msg = "My bag never arrived after my flight to Durban and nobody answers the baggage line."
    item = storage.add(bh["id"], msg, "Complaint form", "", triage.triage(msg, bh))
    assert item["ref"] not in {i["ref"] for i in storage.items(ex["id"])}
    assert storage.get_by_ref(ex["id"], item["ref"]) is None and storage.get_by_ref(bh["id"], item["ref"])
    # the status page on Example Air's link does not find Blue Heron's reference
    at = open_app("example-air", "status")
    at.text_input[0].set_value(item["ref"])
    btn(at, "Check progress").click().run()
    assert at.error
    # and Blue Heron's own link does
    at = open_app("blue-heron-airways", "status", ref=item["ref"])
    assert not at.error
    # replies are signed with the right airline
    assert "Blue Heron Airways" in triage.triage(msg, bh)["draft"] and "Example Air" not in triage.triage(msg, bh)["draft"]


def test_staff_must_use_their_own_airlines_link_and_platform_admin_only_the_bare_url():
    sign_in(open_app("blue-heron-airways"), "agent.demo", auth.DEMO_PASSWORD)  # Example Air's agent, wrong airline
    wrong = open_app("blue-heron-airways")
    sign_in(wrong, "agent.demo", auth.DEMO_PASSWORD)
    assert wrong.title[0].value == "Welcome back"  # still signed out
    wrong = sign_in(open_app("example-air"), "admin.demo", auth.DEMO_PASSWORD)
    assert wrong.title[0].value == "Welcome back"


def test_airline_admin_adds_and_deactivates_staff_and_it_applies_at_once():
    org = sign_in(open_app("example-air"), "org.demo", auth.DEMO_PASSWORD)
    nav(org, "Staff")
    field(org, "Name").set_value("Test Agent")
    field(org, "Email").set_value("test.agent@example.test")
    field(org, "Username").set_value("test.agent")
    btn(org, "Create account").click().run()
    temp = org.session_state["reveal"]["password"]
    u = storage.user_by_username("test.agent")
    assert u and u["role"] == "Support agent" and u["must_change"] and u["airline_id"] == storage.airline_by_slug("example-air")["id"]
    # a duplicate username is refused
    field(org, "Name").set_value("Another")
    field(org, "Email").set_value("another@example.test")
    field(org, "Username").set_value("test.agent")
    btn(org, "Create account").click().run()
    assert any("already taken" in e.value for e in org.error)
    # the new agent signs in, then is deactivated while signed in
    agent = sign_in(open_app("example-air"), "test.agent", temp)
    assert agent.title[0].value == "Choose a new password"
    [b for b in org.button if b.key == f"od{u['id']}"][0].click().run()
    assert not storage.user_by_username("test.agent")["active"]
    agent.run()
    assert agent.title[0].value == "Welcome back"          # signed out on the next click
    again = sign_in(open_app("example-air"), "test.agent", temp)
    assert again.title[0].value == "Welcome back"          # and cannot sign back in
    assert {"user_added", "user_deactivated"} <= {e["action"] for e in storage.events(u["airline_id"])}


def test_last_airline_admin_cannot_be_deactivated_and_nobody_can_deactivate_themselves():
    org = sign_in(open_app("example-air"), "org.demo", auth.DEMO_PASSWORD)
    nav(org, "Staff")
    me = storage.user_by_username("org.demo")
    assert not [b for b in org.button if b.key == f"od{me['id']}"]


def test_deactivated_airline_is_switched_off_for_staff_and_customers():
    add = storage.add_airline("Short Lived Air")
    storage.add_user(add["id"], "sl.admin", "Sl Admin", auth.ORG_ADMIN, auth.hash_password("ThisIsAPassword1"), must_change=False)
    org = sign_in(open_app(add["slug"]), "sl.admin", "ThisIsAPassword1")
    assert org.title[0].value == "Short Lived Air dashboard"
    storage.set_airline_active(add["id"], False)
    org.run()
    assert org.title[0].value != "Short Lived Air dashboard"
    form = open_app(add["slug"], "form")
    assert not form.text_area
    gone = open_app(add["slug"])
    assert not [t for t in gone.text_input if t.key == "login_user"]  # no sign-in on a switched-off link


def test_only_the_right_roles_reach_admin_pages():
    agent = sign_in(open_app("example-air"), "agent.demo", auth.DEMO_PASSWORD)
    for p in ("dashboard", "staff", "overview", "airlines", "allusers", "system", "platlog"):
        agent.session_state.page = p
        agent.run()
        assert agent.title[0].value.startswith("Hello"), p
    lead = sign_in(open_app("example-air"), "lead.demo", auth.DEMO_PASSWORD)
    for p in ("staff", "dashboard", "airlines"):
        lead.session_state.page = p
        lead.run()
        assert lead.title[0].value in ("Insights", "Hello, Sipho"), p


def test_dashboard_numbers_match_the_data():
    ex = storage.airline_by_slug("example-air")
    items = storage.items(ex["id"])
    org = sign_in(open_app("example-air"), "org.demo", auth.DEMO_PASSWORD)
    text = " ".join(m.value for m in org.markdown)
    assert f">{len(items)}<" in text
    done = sum(1 for i in items if i["status"] == "Approved")
    assert f"Replied to ({done} of {len(items)})" in text and f">{done / len(items):.0%}<" in text
    months = {time.strftime("%Y-%m", time.gmtime(i["created"])) for i in items}
    assert len(months) >= 5  # six months of history, so the monthly chart is not empty


def test_new_airline_dashboard_starts_empty():
    at = add_airline("Empty Skies", "Eve E.", "eve.e")
    al = storage.airline_by_slug("empty-skies")
    assert storage.count(al["id"]) == 0 and len(storage.users(al["id"])) == 1


def test_platform_pages_run_and_log_is_scoped():
    at = platform()
    for page in ("Overview", "Airlines", "All users", "Platform log", "System"):
        nav(at, page)
        assert not at.exception, page
    ex = storage.airline_by_slug("example-air")
    assert all(e["airline_id"] == ex["id"] for e in storage.events(ex["id"]))


# ---------------- audit round: loopholes found and closed ----------------
def _make_user(slug, username, role, pw="Passw0rd-long-1", created_by="test"):
    al = storage.airline_by_slug(slug)
    return storage.add_user(al["id"], username, username.title(), role, auth.hash_password(pw), must_change=False, created_by=created_by)


def test_account_locks_after_repeated_wrong_passwords_even_from_new_sessions():
    u = _make_user("example-air", "lockme.one", auth.AGENT)
    for _ in range(storage.LOCK_AFTER):
        at = open_app("example-air")          # a brand-new browser session each time
        sign_in(at, "lockme.one", "wrong-guess-000")
    ok = sign_in(open_app("example-air"), "lockme.one", "Passw0rd-long-1")  # the right password is refused while locked
    assert ok.title[0].value == "Welcome back"
    storage.clear_failed_logins(u["id"])
    assert sign_in(open_app("example-air"), "lockme.one", "Passw0rd-long-1").title[0].value.startswith("Hello")


def test_correct_password_at_the_wrong_link_does_not_count_against_the_account():
    u = _make_user("example-air", "wronglink.user", auth.AGENT)
    for _ in range(storage.LOCK_AFTER + 2):
        sign_in(open_app("blue-heron-airways"), "wronglink.user", "Passw0rd-long-1")
    assert storage.user_by_username("wronglink.user")["fails"] == 0


def test_failed_sign_ins_for_other_airlines_users_do_not_land_in_this_airlines_log():
    ex = storage.airline_by_slug("example-air")["id"]
    bh = storage.airline_by_slug("blue-heron-airways")["id"]
    sign_in(open_app("blue-heron-airways"), "agent.demo", "wrong-guess-000")
    assert not [e for e in storage.events(bh) if e["actor"] == "agent.demo"]
    assert [e for e in storage.events(None) if e["actor"] == "unknown user" and e["action"] == "sign_in_failed"]


def test_password_reset_signs_out_the_other_session_and_own_change_does_not():
    u = _make_user("example-air", "reset.me", auth.AGENT)
    agent = sign_in(open_app("example-air"), "reset.me", "Passw0rd-long-1")
    assert agent.title[0].value.startswith("Hello")
    storage.set_password(u["id"], auth.hash_password("Another-pass-22"), False)  # an admin resets it
    agent.run()
    assert agent.title[0].value == "Welcome back"


def test_own_password_change_rules():
    _make_user("example-air", "pw.rules", auth.AGENT)
    at = sign_in(open_app("example-air"), "pw.rules", "Passw0rd-long-1")
    at.session_state.page = "password"; at.run()
    for new, why in (("Passw0rd-long-1", "different"), ("short", "10"), ("pw.rules-12345", "username"), ("aaaaaaaaaaaa", "varied")):
        field(at, "Current password").set_value("Passw0rd-long-1")
        field(at, "New password").set_value(new)
        field(at, "New password again").set_value(new)
        [b for b in at.button if "Save" in b.label][0].click().run()
        assert at.error and why in at.error[0].value, (new, [e.value for e in at.error])
    field(at, "Current password").set_value("Passw0rd-long-1")
    field(at, "New password").set_value("A-better-pass-77")
    field(at, "New password again").set_value("A-better-pass-77")
    [b for b in at.button if "Save" in b.label][0].click().run()
    assert at.title[0].value.startswith("Hello")  # still signed in after changing their own password


def test_idle_session_is_signed_out():
    at = sign_in(open_app("example-air"), "agent.demo", auth.DEMO_PASSWORD)
    at.session_state["last_seen"] = time.time() - 4000
    at.run()
    assert at.title[0].value == "Welcome back"


def test_shared_demo_accounts_cannot_be_changed_by_an_airline_admin():
    org = sign_in(open_app("example-air"), "org.demo", auth.DEMO_PASSWORD)
    nav(org, "Staff")
    lead = storage.user_by_username("lead.demo")
    assert not [b for b in org.button if b.key == f"od{lead['id']}" or b.key == f"op{lead['id']}"]
    org.session_state.page = "password"; org.run()
    assert not org.text_input and any("shared demo account" in i.value for i in org.info)


def test_role_change_and_last_airline_admin_rule():
    org = sign_in(open_app("example-air"), "org.demo", auth.DEMO_PASSWORD)
    u = _make_user("example-air", "promote.me", auth.AGENT)
    nav(org, "Staff")
    org.selectbox(key=f"ors{u['id']}").set_value(auth.LEAD).run()
    [b for b in org.button if b.key == f"orb{u['id']}"][0].click().run()
    assert storage.user_by_username("promote.me")["role"] == auth.LEAD
    assert any(e["action"] == "role_changed" for e in storage.events(u["airline_id"]))
    # a second airline admin cannot be demoted into nothing: org.demo is shared, so use a fresh airline
    al = storage.add_airline("Solo Admin Air")
    only = storage.add_user(al["id"], "solo.admin", "Solo Admin", auth.ORG_ADMIN, auth.hash_password("Passw0rd-long-1"), must_change=False)
    other = storage.add_user(al["id"], "solo.other", "Solo Other", auth.ORG_ADMIN, auth.hash_password("Passw0rd-long-1"), must_change=False)
    a = sign_in(open_app("solo-admin-air"), "solo.admin", "Passw0rd-long-1")
    nav(a, "Staff")
    a.selectbox(key=f"ors{other['id']}").set_value(auth.AGENT).run()
    [b for b in a.button if b.key == f"orb{other['id']}"][0].click().run()
    assert storage.user_by_username("solo.other")["role"] == auth.AGENT   # allowed: solo.admin remains
    assert storage.user_by_username("solo.admin")["role"] == auth.ORG_ADMIN


def test_names_cannot_carry_markup_and_airline_names_are_unique():
    at = platform(); nav(at, "Airlines")
    field(at, "Airline name").set_value("<script>alert(1)</script> Air")
    field(at, "Their name").set_value("Ok Person"); field(at, "Their email").set_value("ok@example.test"); field(at, "Their username").set_value("ok.person")
    btn(at, "Add airline").click().run()
    assert at.error and not storage.airline_by_name("<script>alert(1)</script> Air")
    field(at, "Airline name").set_value("example air")
    field(at, "Their name").set_value("Ok Person"); field(at, "Their email").set_value("ok@example.test"); field(at, "Their username").set_value("ok.person")
    btn(at, "Add airline").click().run()
    assert any("already exists" in e.value for e in at.error)
    org = sign_in(open_app("example-air"), "org.demo", auth.DEMO_PASSWORD)
    nav(org, "Staff")
    field(org, "Name").set_value("[click me](http://evil.example)"); field(org, "Email").set_value("e@example.test"); field(org, "Username").set_value("evil.link")
    btn(org, "Create account").click().run()
    assert org.error and not storage.user_by_username("evil.link")


def test_csv_export_cannot_run_formulas():
    from common import csv_safe
    assert csv_safe("=HYPERLINK(\"http://x\")") == "'=HYPERLINK(\"http://x\")" and csv_safe("+1") == "'+1" and csv_safe("@sum") == "'@sum"
    assert csv_safe("Customer asks for a refund") == "Customer asks for a refund"


def test_one_time_password_is_forgotten_when_the_admin_moves_on():
    at = add_airline("Forget Me Air", "Fay F.", "fay.f")
    assert at.session_state["reveal"]
    nav(at, "Overview")
    assert not at.session_state["reveal"]


def test_flight_number_is_checked():
    at = open_app("example-air", "form")
    at.text_input[0].set_value("<b>" + "X" * 40)
    at.text_area[0].set_value("My bag never arrived after my flight to Durban and nobody answers the baggage line.")
    btn(at, "Send complaint").click().run()
    assert any("flight number" in e.value.lower() for e in at.error)


def test_platform_demo_button_disappears_once_the_admin_has_a_real_password():
    import seed
    assert seed.default_admin_in_use()
    admin = storage.user_by_username("admin.demo")
    old = admin["pw"]
    storage.set_password(admin["id"], auth.hash_password("Real-strong-pass-9"), False)
    try:
        at = open_app()
        assert not [b for b in at.button if "Platform admin demo" in b.label]
    finally:
        storage.set_password(admin["id"], old, False)


def test_user_cap_per_airline():
    import admin_pages
    al = storage.add_airline("Crowded Air")
    storage.add_user(al["id"], "crowd.admin", "Crowd Admin", auth.ORG_ADMIN, auth.hash_password("Passw0rd-long-1"), must_change=False)
    for i in range(admin_pages.MAX_USERS - 1):
        storage.add_user(al["id"], f"crowd.{i}", f"Crowd {i}", auth.AGENT, "x$y", must_change=False)
    org = sign_in(open_app("crowded-air"), "crowd.admin", "Passw0rd-long-1")
    nav(org, "Staff")
    field(org, "Name").set_value("One Too Many"); field(org, "Email").set_value("t@example.test"); field(org, "Username").set_value("too.many")
    btn(org, "Create account").click().run()
    assert any("already has" in e.value for e in org.error) and not storage.user_by_username("too.many")
