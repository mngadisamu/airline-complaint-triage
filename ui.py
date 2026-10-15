"""Look and feel: neutral slate and white, one dark accent, rounded cards, friendly type. Pure styling, no logic."""
import streamlit as st
import triage

APP_NAME = "Tower"  # the product name: change this one line to rename the tool

DARK, DARK2 = "#0F1A2B", "#1C2B40"       # deep slate: buttons, dark surfaces
BG, LINE, MUTED, TEXT = "#F6F7F9", "#E3E7EC", "#5B6675", "#101828"
CAT = {  # colour, soft background, text colour on the soft background
    "High": ("#C2331F", "#FDE7E3", "#8A2414"),
    "Medium": ("#D99100", "#FFF1D1", "#6B4A00"),
    "Low": ("#4F7CAC", "#E3EDF8", "#214B78"),
    "Review": ("#6B7C8C", "#E8ECF0", "#374554"),
}
CAT_NAME = {"High": "High", "Medium": "Medium", "Low": "Low", "Review": "Needs review"}

BASE_CSS = f"""
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;700;800&display=swap" rel="stylesheet">
<style>
html, body, [class*="css"], .stApp, button, input, textarea {{font-family:'Plus Jakarta Sans',system-ui,sans-serif !important;}}
header[data-testid="stHeader"] {{background:transparent;}}
.stAppDeployButton, #MainMenu, footer {{display:none !important;}}
.stApp {{background:{BG};color:{TEXT}}}
h1,h2,h3 {{letter-spacing:-0.02em;font-weight:800 !important;color:inherit}}
h1 {{font-size:2.3rem !important}}
.block-container {{padding-top:2.2rem;max-width:1280px}}
div[data-baseweb="input"] > div, div[data-baseweb="textarea"] > div, div[data-baseweb="base-input"] {{
  border-radius:14px !important;border:1.5px solid #D5DBE3 !important;background:#fff !important;}}
div[data-baseweb="input"] input, textarea {{font-size:16px !important;color:{TEXT} !important;}}
div[data-baseweb="input"] > div:focus-within, div[data-baseweb="textarea"] > div:focus-within {{
  border-color:{DARK2} !important;box-shadow:0 0 0 3px rgba(15,26,43,.14) !important;}}
label p {{font-weight:700 !important;color:inherit}}
.stButton>button, .stFormSubmitButton>button {{border-radius:999px;min-height:46px;font-weight:700;padding:0 22px;
  border:1.5px solid #D5DBE3;background:#fff;color:{TEXT};transition:transform .12s, box-shadow .12s;}}
.stButton>button:hover, .stFormSubmitButton>button:hover {{border-color:{DARK2};transform:translateY(-1px);box-shadow:0 6px 16px rgba(15,26,43,.10);color:{TEXT}}}
.stButton>button[kind^="primary"], .stFormSubmitButton>button[kind^="primary"] {{background:{DARK};border-color:{DARK};color:#fff;}}
.stButton>button[kind^="primary"]:hover, .stFormSubmitButton>button[kind^="primary"]:hover {{background:{DARK2};color:#fff}}
.stButton>button:disabled {{opacity:.45}}

/* sidebar: light, calm, sectioned */
[data-testid="stSidebar"] {{background:#fff;border-right:1px solid {LINE}}}
[data-testid="stSidebarUserContent"] {{padding:1.4rem 1rem 1rem}}
[data-testid="stSidebarUserContent"] > div > [data-testid="stVerticalBlock"] {{min-height:calc(100vh - 3rem)}}
[data-testid="stLayoutWrapper"]:has(> .st-key-sbfoot) {{margin-top:auto}}
[data-testid="stSidebar"] .stButton>button {{background:transparent;border:0;border-radius:12px;min-height:46px;padding:0 14px;
  color:#344054;font-weight:600;font-size:15px;width:100%;justify-content:flex-start}}
[data-testid="stSidebar"] .stButton>button > div {{justify-content:flex-start;width:100%}}
[data-testid="stSidebar"] .stButton>button p {{text-align:left}}
[data-testid="stSidebar"] .stButton>button:hover {{background:#F1F4F8;box-shadow:none;transform:none;color:{TEXT}}}
[data-testid="stSidebar"] .stButton>button[kind^="primary"] {{background:#E9EEF5;color:{TEXT};font-weight:800}}
.sb-label {{display:flex;align-items:center;gap:10px;font-size:11.5px;font-weight:800;letter-spacing:.12em;color:#6B7686;padding:0 6px 8px}}
.sb-label::after {{content:"";flex:1;height:1px;background:{LINE}}}
.sb-row {{display:flex;align-items:center;gap:10px;padding:9px 10px;font-size:14.5px;font-weight:600;color:#344054}}
.sb-row .dot {{flex:0 0 9px}}
.sb-row b {{margin-left:auto;background:#EEF1F5;color:#344054;border-radius:999px;padding:1px 10px;font-size:13px}}
.sb-user {{display:flex;align-items:center;gap:12px;padding:12px;border-radius:18px;background:{BG};border:1px solid {LINE};margin-bottom:10px}}
.sb-av {{width:42px;height:42px;border-radius:50%;background:{DARK};color:#fff !important;display:flex;align-items:center;justify-content:center;font-weight:800;flex:0 0 42px}}
.sb-name {{font-weight:800;color:{TEXT};line-height:1.2}}
.sb-role {{font-size:13px;color:{MUTED}}}
.sb-note {{font-size:12px;color:#8892A0;line-height:1.5;padding:10px 6px 0}}
[data-testid="stSidebar"] .st-key-signout button {{border:1.5px solid #D5DBE3;justify-content:center;background:#fff}}
[data-testid="stSidebar"] .st-key-signout button > div {{justify-content:center}}

/* keyed containers act as white cards */
.st-key-detail {{background:#fff;border:1px solid {LINE};border-radius:22px;padding:22px 24px}}
.st-key-card {{background:#fff;color:{TEXT};border-radius:28px;padding:26px 28px;box-shadow:0 30px 60px rgba(0,0,0,.25)}}
.st-key-card h1, .st-key-card h2, .st-key-card h3 {{color:{TEXT}}}

.card {{background:#fff;border:1px solid {LINE};border-radius:22px;padding:22px 24px;box-shadow:0 1px 2px rgba(15,26,43,.04)}}
.muted {{color:{MUTED};font-size:14px}}
.chip {{display:inline-flex;align-items:center;gap:7px;border-radius:999px;padding:5px 12px;font-size:13px;font-weight:700}}
.dot {{width:9px;height:9px;border-radius:50%;display:inline-block}}
.stat {{background:#fff;border:1px solid {LINE};border-radius:22px;padding:18px 20px}}
.stat .n {{font-size:2.3rem;font-weight:800;line-height:1.05;letter-spacing:-.02em}}
.stat .l {{color:{MUTED};font-size:14px;margin-top:4px}}
.stat.dark {{background:{DARK};border-color:{DARK};color:#fff}}
.stat.dark .l {{color:#B9C4D3}}
.stat.dark .n {{color:#fff}}
.live {{display:inline-flex;align-items:center;gap:8px;font-size:14px;color:{MUTED};font-weight:600}}
.live i {{width:9px;height:9px;border-radius:50%;background:#2E8B63;box-shadow:0 0 0 0 rgba(46,139,99,.6);animation:pulse 1.8s infinite}}
@keyframes pulse {{70%{{box-shadow:0 0 0 9px rgba(46,139,99,0)}}100%{{box-shadow:0 0 0 0 rgba(46,139,99,0)}}}}
.steps {{display:flex;align-items:center;gap:0;margin:6px 0 2px}}
.step {{display:flex;align-items:center;gap:8px;font-weight:700;font-size:14px;color:{MUTED}}}
.step b {{width:28px;height:28px;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;border:2px solid #D5DBE3;background:#fff;font-size:13px}}
.step.done b {{background:{DARK};border-color:{DARK};color:#fff}}
.step.now b {{border-color:{DARK};color:{DARK}}}
.step.done, .step.now {{color:{TEXT}}}
.bar {{flex:1;height:2px;background:#D5DBE3;margin:0 10px;min-width:20px}}
.bar.done {{background:{DARK}}}
.meter {{height:8px;background:#E6EAF0;border-radius:999px;overflow:hidden;margin-top:8px}}
.meter > div {{height:8px;background:{DARK2};border-radius:999px}}
.tile {{background:{BG};border-radius:18px;padding:14px 16px;min-height:140px}}
.tile .k {{font-size:12px;font-weight:700;color:{MUTED};letter-spacing:.02em}}
.tile .v {{font-size:18px;font-weight:800;margin-top:4px;line-height:1.25}}
.quote {{font-size:1.45rem;line-height:1.4;font-weight:600;letter-spacing:-.01em;margin:14px 0 4px}}
.check {{display:inline-flex;align-items:center;gap:6px;background:#EEF1F5;color:#344054;border-radius:999px;padding:5px 12px;font-size:13px;font-weight:700;margin:0 6px 6px 0}}
.check.bad {{background:#FDE7E3;color:#8A2414}}
.bubble {{background:#fff;border-radius:6px 22px 22px 22px;padding:18px 20px;line-height:1.6;border:1px solid {LINE}}}
.hbar {{display:flex;align-items:center;gap:12px;margin:9px 0;font-size:14px}}
.hbar .t {{flex:0 0 190px;font-weight:600}}
.hbar .b {{flex:1;height:12px;background:#E6EAF0;border-radius:999px;overflow:hidden}}
.hbar .b div {{height:12px;border-radius:999px;background:{DARK2}}}
.hbar .v {{flex:0 0 52px;text-align:right;font-weight:700}}
</style>
"""

PUBLIC_CSS = f"""
<style>
.stApp {{background:{DARK};color:#fff}}
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"] {{display:none !important}}
.block-container {{max-width:1180px;padding-top:2.5rem}}
h1 {{color:#fff;font-size:3.1rem !important;line-height:1.04}}
</style>
"""

LOGIN_CSS = f"""
<style>
.stApp {{background:#fff;color:{TEXT}}}
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"] {{display:none !important}}
.block-container {{max-width:100% !important;padding:0 !important}}
[data-testid="stHorizontalBlock"] {{gap:0 !important}}
header[data-testid="stHeader"] {{display:none}}
.hero {{margin-top:-2rem}}
[data-testid="stColumn"]:nth-child(2) {{padding:8vh 8% 4vh !important;max-width:680px}}
[data-testid="stColumn"] [data-testid="stColumn"]:nth-child(2) {{padding:0 !important;max-width:none}}
.hero {{background:{DARK};min-height:100vh;padding:48px 56px;color:#fff;position:relative;overflow:hidden;box-sizing:border-box}}
.hero h2 {{font-size:3rem;line-height:1.05;margin:60px 0 14px;max-width:11em;color:#fff}}
.hero p {{color:#B9C4D3;font-size:1.1rem;line-height:1.55;max-width:26em}}
.float {{background:#fff;color:{TEXT};border-radius:22px;padding:16px 18px;width:min(380px,100%);margin-top:34px;box-shadow:0 24px 50px rgba(0,0,0,.35);transform:rotate(-2deg)}}
.float .row {{display:flex;gap:10px;align-items:flex-start;padding:10px 0;border-top:1px solid {LINE}}}
.float .row:first-of-type {{border-top:0}}
.float .t {{font-size:14px;line-height:1.35;font-weight:600}}
.float .s {{font-size:12px;color:{MUTED};margin-top:2px}}
.arc {{position:absolute;right:-120px;bottom:-140px;opacity:.9}}
</style>
"""


from html import escape as esc


def H(html: str):
    """Render HTML without markdown treating indented lines as code."""
    st.markdown("\n".join(l.strip() for l in html.splitlines() if l.strip()), unsafe_allow_html=True)


def plane(color):
    return f'<svg width="28" height="28" viewBox="0 0 24 24" fill="none"><path d="M21 3L3 10.5l6 2.5 2.5 6L21 3z" fill="{color}"/></svg>'


def brand(dark=True, product=True, org=None, platform=False):
    """Staff screens show the tool (Tower, for the airline). Customer screens show only the airline.
    org = the airline's name (defaults to the config file's); platform=True is the platform admin's view."""
    col, pl, sub = ("#fff", "#fff", "#9FB0C7") if dark else (TEXT, DARK, MUTED)
    name = esc(org or triage.AIRLINE)
    if not product:
        return f'<div style="display:flex;align-items:center;gap:10px;font-weight:800;font-size:20px;color:{col}">{plane(pl)}{name}</div>'
    line = "platform admin" if platform else f"for {name}"
    return (f'<div style="display:flex;align-items:center;gap:12px;color:{col}">{plane(pl)}'
            f'<div style="line-height:1.15"><div style="font-weight:800;font-size:21px;letter-spacing:-.01em">{APP_NAME}</div>'
            f'<div style="font-size:12px;font-weight:600;color:{sub}">{line}</div></div></div>')


def chip(cat, label=None):
    c, bg, tx = CAT[cat]
    return f'<span class="chip" style="background:{bg};color:{tx}"><span class="dot" style="background:{c}"></span>{label or CAT_NAME[cat]}</span>'


def stepper(labels, current):
    """current = index of the step in progress; earlier steps are done."""
    out = []
    for i, lab in enumerate(labels):
        cls = "done" if i < current else ("now" if i == current else "")
        mark = "✓" if i < current else str(i + 1)
        out.append(f'<div class="step {cls}"><b>{mark}</b>{lab}</div>')
        if i < len(labels) - 1:
            out.append(f'<div class="bar {"done" if i < current else ""}"></div>')
    return f'<div class="steps">{"".join(out)}</div>'


def gauge(pct, label, sub):
    r, c = 62, 2 * 3.14159 * 62
    return f"""<div style="display:flex;align-items:center;gap:20px;flex-wrap:wrap">
<svg width="150" height="150" viewBox="0 0 150 150"><circle cx="75" cy="75" r="{r}" fill="none" stroke="#E6EAF0" stroke-width="14"/>
<circle cx="75" cy="75" r="{r}" fill="none" stroke="{DARK2}" stroke-width="14" stroke-linecap="round" stroke-dasharray="{c*pct:.1f} {c:.1f}" transform="rotate(-90 75 75)"/>
<text x="75" y="82" text-anchor="middle" font-size="30" font-weight="800" fill="{TEXT}">{pct:.0%}</text></svg>
<div><div style="font-weight:800;font-size:18px">{label}</div><div class="muted" style="max-width:15em">{sub}</div></div></div>"""


def hbars(rows, fmt=lambda v: f"{v:.0%}", maxv=1.0):
    out = []
    for name, v in rows:
        w = max(2, min(100, v / maxv * 100))
        out.append(f'<div class="hbar"><div class="t">{esc(name)}</div><div class="b"><div style="width:{w:.0f}%"></div></div><div class="v">{fmt(v)}</div></div>')
    return "".join(out)
