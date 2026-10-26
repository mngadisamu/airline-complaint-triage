"""Small helpers shared by the app and the admin pages."""
import html as _html, re, time
import streamlit as st
import storage

ss = st.session_state

ACTION_LABELS = {
    "received": "Complaint received", "ai_draft": "AI draft written", "ai_draft_failed": "AI draft failed",
    "escalated": "Escalated to team lead", "returned": "Returned to queue", "approved": "Reply approved",
    "signed_in": "Signed in", "signed_out": "Signed out", "sign_in_failed": "Sign-in failed",
    "user_added": "User added", "user_deactivated": "User deactivated", "user_reactivated": "User reactivated",
    "password_reset": "Password reset", "password_changed": "Password changed",
    "role_changed": "Role changed", "follow_up": "Customer follow-up", "email_changed": "Email changed", "name_changed": "Name changed", "airline_edited": "Airline details changed", "credentials_emailed": "Sign-in details emailed", "airline_added": "Airline added", "airline_deactivated": "Airline deactivated", "airline_reactivated": "Airline reactivated",
}


def esc(t):
    return _html.escape(t or "")


def md_esc(t):
    return re.sub(r"([\\`*_{}\[\]<>#$~|])", r"\\\1", t)


def when(ts):
    return time.strftime("%d %b %Y %H:%M", time.gmtime(ts)) + " UTC"


def audit(action, ref="", detail="", airline_id=None):
    """Write to the activity log as whoever is signed in (or as the customer when nobody is).
    A platform admin's actions go to the platform log (airline_id empty) and only record which airline they were about."""
    u = ss.get("user")
    name, role = (u["name"], u["role"]) if u else ("customer", "customer")
    aid = airline_id if airline_id is not None else (u["airline_id"] if u else None)
    uid = u["id"] if u else None
    if u and u["role"] == "Platform admin":
        storage.log(None, name, role, action, ref, detail, about=aid, actor_id=uid)
    else:
        storage.log(aid, name, role, action, ref, detail, actor_id=uid)


def flash(msg):
    ss.flash = msg  # shown once on the next screen


def base_url():
    """The address people used to reach the app, to build the links an airline hands out (APP_URL in the secrets overrides it)."""
    import mailer
    fixed = (mailer.setting("APP_URL") or "").strip().rstrip("/")
    if fixed.startswith(("http://", "https://")):
        return fixed
    try:
        host = st.context.headers.get("Host") or "localhost:8501"
    except Exception:
        host = "localhost:8501"
    return ("http" if host.startswith(("localhost", "127.")) else "https") + "://" + host


def airline_links(al):
    b = f"{base_url()}/?airline={al['slug']}"
    return {"Staff sign-in": b, "Complaint form for customers": b + "&view=form", "Status page for customers": b + "&view=status"}


NAME_OK = re.compile(r"^[A-Za-z0-9\u00C0-\u024F][A-Za-z0-9\u00C0-\u024F .'&-]{1,59}$")


def clean_name(t):
    """A person's or airline's name: letters, numbers, spaces and . ' & - only (no markup, links or line breaks). None if not acceptable."""
    t = " ".join((t or "").split())
    return t if NAME_OK.match(t) else None


def csv_safe(v):
    """Stop spreadsheet programs treating a cell as a formula (a note starting with = + - @ could otherwise run)."""
    v = "" if v is None else str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


def sign_out(message=None):
    """Forget everything about this browser session (drafts, selected complaint, one-time passwords), then optionally leave a note."""
    ss.clear()
    if message:
        ss.flash = message


EMAIL_OK = re.compile(r"^[^@\s<>\"',;]{1,64}@[A-Za-z0-9.-]{1,190}\.[A-Za-z]{2,}$")


def valid_email(e):
    return bool(EMAIL_OK.match((e or "").strip()))
