"""Optional email, used to send new people their sign-in details.
Set SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASSWORD and SMTP_FROM in the app's secrets (or environment).
Without them nothing is sent: the admin is shown the details once instead, with a ready-made email to send themselves."""
import os, smtplib, ssl
from html import escape as esc
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


def send(to, subject, body, html=None):
    """Returns (True, "") on success, or (False, reason). The reason never contains the password or the message."""
    if not configured():
        return False, "Email is not set up on this system"
    try:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = setting("SMTP_FROM"), to, subject
        msg.set_content(body)
        if html:
            msg.add_alternative(html, subtype="html")  # plain text stays as the fallback
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


# Colours match the sign-in page (see ui.py). Email apps ignore most CSS and all SVG, so this is plain tables with inline styles.
DARK, BG, LINE, MUTED, TEXT = "#0F1A2B", "#F6F7F9", "#E3E7EC", "#5B6675", "#101828"
FONT = "'Plus Jakarta Sans',-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"


def _page(product, airline, heading, intro, rows, button_text, link, note):
    """One branded email: dark header like the sign-in page, a white card with the details, and a pill button."""
    detail = "".join(
        f'<tr><td style="padding:12px 0;border-top:1px solid {LINE};font-size:13px;color:{MUTED};width:38%">{esc(k)}</td>'
        f'<td style="padding:12px 0;border-top:1px solid {LINE};font-size:15px;font-weight:700;color:{TEXT};'
        f'{"font-family:Consolas,Menlo,monospace;letter-spacing:.03em;" if mono else ""}">{esc(v)}</td></tr>' for k, v, mono in rows)
    return f"""<!doctype html><html><body style="margin:0;padding:0;background:{BG};font-family:{FONT};color:{TEXT}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG};padding:24px 12px"><tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="width:100%;max-width:560px">
<tr><td style="background:{DARK};border-radius:22px 22px 0 0;padding:28px 32px">
<table role="presentation" cellpadding="0" cellspacing="0"><tr>
<td style="font-size:26px;line-height:1;color:#fff;padding-right:12px">&#9992;</td>
<td style="color:#fff"><div style="font-size:21px;font-weight:800;letter-spacing:-.01em;line-height:1.15">{esc(product)}</div>
<div style="font-size:12px;font-weight:600;color:#9FB0C7">for {esc(airline)}</div></td></tr></table>
<div style="font-size:26px;line-height:1.2;font-weight:800;color:#fff;margin-top:26px">{esc(heading)}</div>
</td></tr>
<tr><td style="background:#fff;border-radius:0 0 22px 22px;padding:28px 32px 32px">
<p style="margin:0 0 20px;font-size:15px;line-height:1.55;color:{TEXT}">{intro}</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:26px">{detail}<tr><td colspan="2" style="border-top:1px solid {LINE};font-size:0;line-height:0">&nbsp;</td></tr></table>
<table role="presentation" cellpadding="0" cellspacing="0"><tr><td style="background:{DARK};border-radius:999px">
<a href="{esc(link, quote=True)}" style="display:inline-block;padding:14px 28px;font-size:15px;font-weight:700;color:#fff;text-decoration:none;font-family:{FONT}">{esc(button_text)}</a></td></tr></table>
<p style="margin:22px 0 0;font-size:13px;line-height:1.55;color:{MUTED}">{note}</p>
<p style="margin:14px 0 0;font-size:12px;line-height:1.5;color:{MUTED}">Button not working? Copy this address into your browser:<br>
<span style="color:{TEXT};word-break:break-all">{esc(link)}</span></p>
</td></tr>
<tr><td style="padding:16px 8px;text-align:center;font-size:12px;color:{MUTED}">Sent by {esc(product)}. Please do not forward this email.</td></tr>
</table></td></tr></table></body></html>"""


def welcome(name, airline, role, username, password, link, product="Tower"):
    """Subject, plain-text body and HTML body of the sign-in email."""
    subject = f"Your {product} sign-in details for {airline}"
    body = (f"Hello {name},\n\nYou have been added to {product} for {airline} as {role}.\n\n"
            f"Sign in here: {link}\nUsername: {username}\nTemporary password: {password}\n\n"
            "You will be asked to choose your own password the first time you sign in. "
            "Please do not forward this email.\n")
    html = _page(product, airline, "You're in. Sign in to get started.",
                 f"Hello {esc(name)},<br><br>You have been added to {esc(product)} for <b>{esc(airline)}</b> as <b>{esc(role)}</b>.",
                 [("Username", username, False), ("Temporary password", password, True)], f"Sign in to {product}", link,
                 "You will be asked to choose your own password the first time you sign in.")
    return subject, body, html


def reset_notice(name, airline, username, password, link, product="Tower"):
    subject = f"Your {product} password was reset"
    body = (f"Hello {name},\n\nAn administrator reset your {product} password for {airline}.\n\n"
            f"Sign in here: {link}\nUsername: {username}\nTemporary password: {password}\n\n"
            "You will be asked to choose a new password. If you did not expect this, tell your administrator.\n")
    html = _page(product, airline, "Your password was reset.",
                 f"Hello {esc(name)},<br><br>An administrator reset your {esc(product)} password for <b>{esc(airline)}</b>.",
                 [("Username", username, False), ("Temporary password", password, True)], f"Sign in to {product}", link,
                 "You will be asked to choose a new password. If you did not expect this, tell your administrator.")
    return subject, body, html


def mailto(to, subject, body):
    return f"mailto:{quote(to)}?subject={quote(subject)}&body={quote(body)}"
