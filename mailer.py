"""Optional email, used to send new people their sign-in details.
Set SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASSWORD and SMTP_FROM in the app's secrets (or environment).
Without them nothing is sent: the admin is shown the details once instead, with a ready-made email to send themselves."""
import os, smtplib, ssl
from email.message import EmailMessage
from urllib.parse import quote


def setting(name, default=None):
    if os.environ.get(name):
        return os.environ[name]
    try:
        import streamlit as st
        return st.secrets.get(name, default)
    except Exception:
        return default


def configured() -> bool:
    return bool(setting("SMTP_HOST") and setting("SMTP_FROM"))


def send(to, subject, body):
    """Returns (True, "") on success, or (False, reason). The reason never contains the password or the message."""
    if not configured():
        return False, "Email is not set up on this system"
    try:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = setting("SMTP_FROM"), to, subject
        msg.set_content(body)
        host, port = setting("SMTP_HOST"), int(setting("SMTP_PORT", 587))
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=20, context=ssl.create_default_context()) as s:
                _login(s)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as s:
                s.starttls(context=ssl.create_default_context())
                _login(s)
                s.send_message(msg)
        return True, ""
    except Exception as e:  # network, login or address problems
        return False, type(e).__name__


def _login(s):
    if setting("SMTP_USER"):
        s.login(setting("SMTP_USER"), setting("SMTP_PASSWORD", ""))


def welcome(name, airline, role, username, password, link, product="Tower"):
    """Subject and body of the sign-in email."""
    subject = f"Your {product} sign-in details for {airline}"
    body = (f"Hello {name},\n\nYou have been added to {product} for {airline} as {role}.\n\n"
            f"Sign in here: {link}\nUsername: {username}\nTemporary password: {password}\n\n"
            "You will be asked to choose your own password the first time you sign in. "
            "Please do not forward this email.\n")
    return subject, body


def reset_notice(name, airline, username, password, link, product="Tower"):
    subject = f"Your {product} password was reset"
    body = (f"Hello {name},\n\nAn administrator reset your {product} password for {airline}.\n\n"
            f"Sign in here: {link}\nUsername: {username}\nTemporary password: {password}\n\n"
            "You will be asked to choose a new password. If you did not expect this, tell your administrator.\n")
    return subject, body


def mailto(to, subject, body):
    return f"mailto:{quote(to)}?subject={quote(subject)}&body={quote(body)}"
