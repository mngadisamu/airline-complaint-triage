"""Triage engine: clean/mask text, classify the reason, rate urgency, route to a team, draft a reply."""
import re
import joblib
from pathlib import Path

import json, os

MODEL_PATH = Path(__file__).parent / "model" / "reason_model.joblib"
CONFIG_PATH = os.environ.get("AIRLINE_CONFIG", str(Path(__file__).parent / "airline.json"))
CONFIG = json.load(open(CONFIG_PATH))  # everything airline-specific
THRESHOLD = CONFIG["confidence_threshold"]
MIN_LEN, MAX_LEN = 10, 1000

REASONS = ["Cancelled Flight", "Lost Luggage", "Late Flight", "Flight Booking Problems",
           "Damaged Luggage", "Customer Service Issue", "Flight Attendant Complaints",
           "Bad Flight", "longlines", "Can't Tell"]
DISPLAY = {"longlines": "Long Lines", "Can't Tell": "Other"}

# Assumption A2 (urgency rules) and A3 (team routing) come from airline.json.
AIRLINE = CONFIG["airline_name"]
SIGN_OFF_TEXT = CONFIG["sign_off"]
SIGN_OFF = "\n\n" + SIGN_OFF_TEXT
HIGH_REASONS = set(CONFIG["high_reasons"])
MEDIUM_REASONS = set(CONFIG["medium_reasons"])
URGENT_WORDS = CONFIG["urgent_words"]
TEAMS = CONFIG["teams"]
MANUAL_TEAM = CONFIG["manual_team"]
DEFAULT_TEAM = CONFIG["default_team"]
BLOCKED_WORDS = CONFIG["blocked_words"]
TEMPLATES = CONFIG["reply_templates"]


def airline_name(airline=None) -> str:
    return airline["name"] if airline else AIRLINE


def sign_off_text(airline=None) -> str:
    return airline["sign_off"] if airline else SIGN_OFF_TEXT


def reply_template(reason: str, airline=None) -> str:
    """Fill the template (shared by all airlines, from airline.json) with the team, and sign it as this airline."""
    team = TEAMS.get(reason, DEFAULT_TEAM)
    return TEMPLATES.get(reason, TEMPLATES["Can't Tell"]).format(team=team) + "\n\n" + sign_off_text(airline)


def followup_template(item, airline=None) -> str:
    """Starting point for the reply to a customer who wrote back. A person edits and approves it, as always."""
    team = item.get("team") or DEFAULT_TEAM
    return (f"Thank you for getting back to us. We have read your message and passed it to the {team} team to look into it. "
            "If you can share your booking reference or flight details, it will help us.\n\n" + sign_off_text(airline))


_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d")
_HANDLE = re.compile(r"@\w+")
_URL = re.compile(r"https?://\S+")


def mask(text: str) -> str:
    """AC7.1/7.2: hide handles, emails and phone numbers."""
    text = _EMAIL.sub("[email hidden]", text)
    text = _PHONE.sub("[number hidden]", text)
    return _HANDLE.sub("@••••••", text)


def clean_for_model(text: str) -> str:
    text = _URL.sub(" ", text)
    text = _HANDLE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def validate(text: str):
    """AC5.2/5.3: returns an error message or None."""
    t = (text or "").strip()
    if len(t) < MIN_LEN:
        return f"Please write at least {MIN_LEN} characters."
    if len(t) > MAX_LEN:
        return f"Please shorten your complaint to {MAX_LEN:,} characters or fewer."
    return None


_model = None


def _load():
    global _model
    if _model is None:
        _model = joblib.load(MODEL_PATH)
    return _model


def urgency(reason: str, text: str):
    low = text.lower()
    hits = [w for w in URGENT_WORDS if w in low]
    if reason in HIGH_REASONS:
        why = f'{DISPLAY.get(reason, reason)} is rated High' + (f', and the text says "{hits[0]}"' if hits else "")
        return "High", why
    if hits:
        return "High", f'The text says "{hits[0]}"'
    if reason in MEDIUM_REASONS:
        return "Medium", f"{DISPLAY.get(reason, reason)} is rated Medium"
    return "Low", f"{DISPLAY.get(reason, reason)} is rated Low"


def safe_reply(draft: str, reason: str, airline=None) -> str:
    """AC4.3: fall back to the template if a promise word appears."""
    low = draft.lower()
    if any(w in low for w in BLOCKED_WORDS) or airline_name(airline) not in draft:
        return reply_template(reason, airline)
    return draft


def triage(text: str, airline=None) -> dict:
    """Return the full suggestion for one complaint."""
    model = _load()
    proba = model.predict_proba([clean_for_model(text)])[0]
    i = int(proba.argmax())
    reason, conf = model.classes_[i], float(proba[i])
    flagged = conf < THRESHOLD
    urg_reason = reason if not flagged else "Can't Tell"
    level, why = urgency(urg_reason, text)
    if flagged:
        # low confidence: never trust the guess, but urgent words still raise urgency
        why = why if level == "High" else f"Only {conf:.0%} sure, so no reason is suggested"
    return {
        "reason": None if flagged else reason,
        "reason_label": "Needs manual review" if flagged else DISPLAY.get(reason, reason),
        "confidence": conf,
        "flagged": flagged,
        "category": "High" if level == "High" else ("Review" if flagged else level),
        "urgency": level,
        "urgency_why": why,
        "team": MANUAL_TEAM if flagged else TEAMS.get(reason, DEFAULT_TEAM),
        "draft": reply_template("Can't Tell", airline) if flagged else reply_template(reason, airline),
    }


def customer_status(item) -> dict:
    """What the customer is allowed to see: progress, and the reply only once a person approved it.
    step = how many stages are finished: 1 Received, 2 Reviewed (a person has looked at it), 3 Reply ready."""
    s = item["status"]
    if s == "Approved":
        return {"label": "Replied", "step": 3, "message": "A member of our team has replied.", "reply": item["final_reply"]}
    if s == "Escalated":  # an agent has read it and passed it up
        return {"label": "With a senior team member", "step": 2,
                "message": "A member of our team has reviewed your complaint and passed it to a senior team member for a decision.", "reply": None}
    if s == "New" and item.get("followups"):  # the customer wrote back after a reply
        return {"label": "Follow-up received", "step": 1, "message": "We have your follow-up. A person will read it and reply here.", "reply": item.get("final_reply")}
    if item.get("note"):  # a team lead reviewed it and sent it back to an agent
        return {"label": "Reviewed", "step": 2,
                "message": "A senior team member has reviewed your complaint. A reply is being prepared.", "reply": None}
    return {"label": "Received", "step": 1, "message": "We have your complaint. A person will read it and approve a reply.", "reply": None}
