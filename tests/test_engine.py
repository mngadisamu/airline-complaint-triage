import time, triage, auth

def test_validate():
    assert triage.validate("") and triage.validate("short") and triage.validate("x" * 1001)
    assert triage.validate("My flight was cancelled yesterday") is None

def test_mask():
    t = triage.mask("@United call me on 082 123 4567 or a.b@mail.com")
    assert "@United" not in t and "082" not in t and "a.b@mail.com" not in t

def test_triage_fields():
    r = triage.triage("My flight was cancelled and I'm stuck at the airport with two kids")
    assert r["urgency"] == "High" and r["team"] in ("Operations", triage.MANUAL_TEAM) and r["draft"].endswith(triage.SIGN_OFF_TEXT)

def test_low_confidence_flag():
    r = triage.triage("ok then whatever happened happened here")
    assert r["flagged"] == (r["confidence"] < triage.THRESHOLD)
    if r["flagged"]:
        assert r["team"] == triage.MANUAL_TEAM and r["reason_label"] == "Needs manual review"

def test_no_promises_in_templates():
    for t in triage.TEMPLATES.values():
        assert not any(w in (t + triage.SIGN_OFF).lower() for w in triage.BLOCKED_WORDS)
    assert "Example Air" in triage.safe_reply("We guarantee a refund", "Late Flight")
    assert "refund" not in triage.safe_reply("We guarantee a refund", "Late Flight").lower()

def test_auth():
    assert auth.check("agent.demo", auth.DEMO_PASSWORD)["role"] == "Support agent"
    assert auth.check("agent.demo", "wrong") is None and auth.check("nobody", "x") is None
    assert auth.locked_for(5, time.time()) > 0 and auth.locked_for(5, time.time() - 61) == 0 and auth.locked_for(4, time.time()) == 0


def test_config_has_everything_needed():
    for k in ("airline_name", "sign_off", "teams", "default_team", "manual_team", "urgent_words", "blocked_words", "reply_templates"):
        assert k in triage.CONFIG
    for reason in triage.REASONS:
        assert "{team}" in triage.TEMPLATES[reason]
        assert triage.AIRLINE in triage.reply_template(reason)

def test_another_airline_by_config_only(tmp_path):
    import json, subprocess, sys, pathlib
    cfg = dict(triage.CONFIG, airline_name="Sky Test Air", sign_off="Sky Test Air Care", teams={"Cancelled Flight": "Disruption Desk"})
    p = tmp_path / "other.json"; p.write_text(json.dumps(cfg))
    code = "import triage; r = triage.triage('My flight was cancelled and we are stuck at the airport'); print(r['team'], '|', r['draft'].splitlines()[-1])"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(pathlib.Path(triage.__file__).parent),
                         env={**__import__("os").environ, "AIRLINE_CONFIG": str(p)}).stdout.strip()
    assert out in ("Disruption Desk | Sky Test Air Care", "Customer Relations (manual) | Sky Test Air Care")


def test_customer_progress_follows_what_staff_did():
    import triage
    base = {"status": "New", "final_reply": None, "note": None}
    assert triage.customer_status(base)["step"] == 1                      # received, nobody has looked yet
    assert triage.customer_status({**base, "status": "Escalated"})["step"] == 2   # an agent reviewed it and passed it up
    assert triage.customer_status({**base, "note": "ok"})["step"] == 2    # lead reviewed and returned it
    done = triage.customer_status({**base, "status": "Approved", "final_reply": "Hi"})
    assert done["step"] == 3 and done["reply"] == "Hi"
    assert triage.customer_status({**base, "status": "Escalated", "final_reply": "draft"})["reply"] is None
