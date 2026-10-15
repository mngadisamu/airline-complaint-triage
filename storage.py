"""SQLite store shared by every session and every airline.
Every complaint, user and log line belongs to one airline (airline_id); every query below filters by it, so one airline
can never read another's data. On Streamlit Community Cloud the file is lost when the app is rebuilt (demo storage)."""
import json, os, re, secrets, sqlite3, time
from pathlib import Path

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I to avoid mix-ups
TRIAGE_KEYS = ("reason", "reason_label", "confidence", "flagged", "urgency", "urgency_why", "team", "draft", "category")


def _path():
    return os.environ.get("TRIAGE_DB", str(Path(__file__).parent / "data" / "complaints.db"))


def db_path():
    return _path()


def _cols(c, table):
    return [r[1] for r in c.execute(f"PRAGMA table_info({table})")]


def _conn():
    Path(_path()).parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(_path(), timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS airlines (
        id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT UNIQUE, name TEXT, sign_off TEXT,
        active INTEGER DEFAULT 1, demo INTEGER DEFAULT 0, created REAL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, airline_id INTEGER, username TEXT UNIQUE, name TEXT, role TEXT, pw TEXT,
        active INTEGER DEFAULT 1, must_change INTEGER DEFAULT 0, created REAL, created_by TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS complaints (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ref TEXT UNIQUE, created REAL, status TEXT,
        source TEXT, flight TEXT, text TEXT, final_reply TEXT, data TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT, airline_id INTEGER, complaint_id INTEGER, ts REAL, sender TEXT, text TEXT, by TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, actor TEXT, role TEXT, action TEXT, ref TEXT, detail TEXT)""")
    # columns added over time: older database files are upgraded in place
    for table, col, ddl in (("complaints", "ai", "TEXT"), ("complaints", "note", "TEXT"),
                            ("complaints", "airline_id", "INTEGER"), ("complaints", "resolved", "REAL"),
                            ("events", "airline_id", "INTEGER"), ("events", "about_id", "INTEGER"),
                            ("complaints", "followups", "INTEGER DEFAULT 0"), ("complaints", "approved_by", "TEXT"),
                            ("users", "email", "TEXT DEFAULT ''"), ("users", "pw_set", "REAL DEFAULT 0"), ("events", "actor_id", "INTEGER"),
                            ("users", "fails", "INTEGER DEFAULT 0"), ("users", "locked_until", "REAL DEFAULT 0")):
        if col not in _cols(c, table):
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
    return c


# ---------- airlines ----------
def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s[:40] or "airline"


def _airline(r):
    d = dict(r) if r else None
    if d:
        d["active"], d["demo"] = bool(d["active"]), bool(d["demo"])
    return d


def add_airline(name, sign_off=None, demo=False):
    name = " ".join((name or "").split())
    base = slug = slugify(name)
    with _conn() as c:
        n = 2
        while c.execute("SELECT 1 FROM airlines WHERE slug=?", (slug,)).fetchone():
            slug, n = f"{base}-{n}", n + 1
        cur = c.execute("INSERT INTO airlines (slug, name, sign_off, active, demo, created) VALUES (?,?,?,?,?,?)",
                        (slug, name, sign_off or f"{name} Customer Care", 1, int(demo), time.time()))
        return _airline(c.execute("SELECT * FROM airlines WHERE id=?", (cur.lastrowid,)).fetchone())


def airlines():
    with _conn() as c:
        return [_airline(r) for r in c.execute("SELECT * FROM airlines ORDER BY id")]


def airline_by_slug(slug):
    with _conn() as c:
        return _airline(c.execute("SELECT * FROM airlines WHERE slug=?", ((slug or "").strip().lower(),)).fetchone())


def airline(airline_id):
    with _conn() as c:
        return _airline(c.execute("SELECT * FROM airlines WHERE id=?", (airline_id,)).fetchone())


def set_airline_active(airline_id, active):
    with _conn() as c:
        c.execute("UPDATE airlines SET active=? WHERE id=?", (int(active), airline_id))


# ---------- users ----------
def _user(r):
    d = dict(r) if r else None
    if d:
        d["active"], d["must_change"] = bool(d["active"]), bool(d["must_change"])
    return d


def add_user(airline_id, username, name, role, pw_hash, must_change=True, created_by="", email=""):
    """Returns the new user, or None if the username is already taken (usernames are unique across the platform)."""
    try:
        with _conn() as c:
            cur = c.execute("INSERT INTO users (airline_id, username, name, role, pw, active, must_change, created, created_by, email, pw_set) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (airline_id, username.strip().lower(), name.strip(), role, pw_hash, 1, int(must_change), time.time(), created_by, (email or "").strip(), time.time()))
            return _user(c.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone())
    except sqlite3.IntegrityError:
        return None


def user_by_username(username):
    with _conn() as c:
        return _user(c.execute("SELECT * FROM users WHERE username=?", ((username or "").strip().lower(),)).fetchone())


def user_by_id(user_id):
    with _conn() as c:
        return _user(c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone())


def users(airline_id=None):
    """airline_id=None lists everyone on the platform (platform admin only)."""
    with _conn() as c:
        if airline_id is None:
            rows = c.execute("SELECT * FROM users ORDER BY id").fetchall()
        else:
            rows = c.execute("SELECT * FROM users WHERE airline_id=? ORDER BY id", (airline_id,)).fetchall()
    return [_user(r) for r in rows]


def set_user_active(user_id, active):
    with _conn() as c:
        c.execute("UPDATE users SET active=? WHERE id=?", (int(active), user_id))


LOCK_AFTER, LOCK_SECONDS = 10, 300  # wrong passwords in a row before an account is locked, and for how long


def note_failed_login(user_id):
    """Count a wrong password against the ACCOUNT (not the browser), so opening new browser sessions does not help a guesser."""
    with _conn() as c:
        c.execute("UPDATE users SET fails=COALESCE(fails,0)+1 WHERE id=?", (user_id,))
        n = c.execute("SELECT fails FROM users WHERE id=?", (user_id,)).fetchone()[0]
        if n >= LOCK_AFTER:
            c.execute("UPDATE users SET fails=0, locked_until=? WHERE id=?", (time.time() + LOCK_SECONDS, user_id))


def clear_failed_logins(user_id):
    with _conn() as c:
        c.execute("UPDATE users SET fails=0, locked_until=0 WHERE id=?", (user_id,))


def set_role(user_id, role):
    with _conn() as c:
        c.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))


def set_email(user_id, email):
    with _conn() as c:
        c.execute("UPDATE users SET email=? WHERE id=?", ((email or "").strip(), user_id))


def airline_by_name(name):
    with _conn() as c:
        return _airline(c.execute("SELECT * FROM airlines WHERE lower(name)=lower(?)", (" ".join((name or "").split()),)).fetchone())


def set_password(user_id, pw_hash, must_change):
    with _conn() as c:
        c.execute("UPDATE users SET pw=?, must_change=?, fails=0, locked_until=0, pw_set=? WHERE id=?", (pw_hash, int(must_change), time.time(), user_id))


# ---------- complaints ----------
def new_ref():
    return "EX-" + "".join(secrets.choice(ALPHABET) for _ in range(8))


def _row(r):
    d = dict(r)
    d.update(json.loads(d.pop("data")))
    d["ai"] = json.loads(d["ai"]) if d.get("ai") else None
    return d


def add(airline_id, text, source, flight, triage_result, age_min=0):
    data = json.dumps({k: triage_result[k] for k in TRIAGE_KEYS})
    with _conn() as c:
        for _ in range(5):
            ref = new_ref()
            try:
                cur = c.execute("INSERT INTO complaints (airline_id, ref, created, status, source, flight, text, final_reply, data) VALUES (?,?,?,?,?,?,?,?,?)",
                                (airline_id, ref, time.time() - age_min * 60, "New", source, flight, text, None, data))
                break
            except sqlite3.IntegrityError:
                continue
        r = c.execute("SELECT * FROM complaints WHERE id=?", (cur.lastrowid,)).fetchone()
    return _row(r)


def items(airline_id):
    with _conn() as c:
        return [_row(r) for r in c.execute("SELECT * FROM complaints WHERE airline_id=? ORDER BY id", (airline_id,))]


def count(airline_id=None):
    with _conn() as c:
        if airline_id is None:
            return c.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
        return c.execute("SELECT COUNT(*) FROM complaints WHERE airline_id=?", (airline_id,)).fetchone()[0]


def get_by_ref(airline_id, ref):
    """A reference only works for the airline whose link the customer used."""
    with _conn() as c:
        r = c.execute("SELECT * FROM complaints WHERE airline_id=? AND ref=?", (airline_id, (ref or "").strip().upper())).fetchone()
    return _row(r) if r else None


def update(airline_id, item_id, **fields):
    assert set(fields) <= {"status", "final_reply", "ai", "note", "resolved", "approved_by"}
    if "ai" in fields and fields["ai"] is not None:
        fields["ai"] = json.dumps(fields["ai"])
    sets = ", ".join(f"{k}=?" for k in fields)
    with _conn() as c:
        c.execute(f"UPDATE complaints SET {sets} WHERE id=? AND airline_id=?", (*fields.values(), item_id, airline_id))


def update_if(airline_id, item_id, expected_status, **fields) -> bool:
    """Change a complaint only if it is still in the status the person saw on screen.
    Returns False when someone else got there first, so a second click cannot overwrite the first."""
    assert set(fields) <= {"status", "final_reply", "ai", "note", "resolved", "approved_by"}
    sets = ", ".join(f"{k}=?" for k in fields)
    with _conn() as c:
        cur = c.execute(f"UPDATE complaints SET {sets} WHERE id=? AND airline_id=? AND status=?",
                        (*fields.values(), item_id, airline_id, expected_status))
        return cur.rowcount == 1


# ---------- activity log: who did what, and when ----------
def log(airline_id, actor, role, action, ref="", detail="", ts=None, about=None, actor_id=None):
    """Append one line to the activity log. Never put full complaint text, passwords or keys in detail.
    about = the airline a platform admin's action concerns. Those lines belong to the platform log, not to the airline's own log."""
    with _conn() as c:
        c.execute("INSERT INTO events (airline_id, ts, actor, role, action, ref, detail, about_id, actor_id) VALUES (?,?,?,?,?,?,?,?,?)",
                  (airline_id, ts or time.time(), actor or "", role or "", action, ref or "", (detail or "")[:300], about, actor_id))


def events(airline_id=None, limit=1000, ref=None):
    """Newest first. airline_id=None means the whole platform (platform admin only)."""
    q, args = "SELECT * FROM events WHERE 1=1", []
    if airline_id is not None:  # an airline sees only its own people and its own customers, never the platform admin's actions
        q += " AND airline_id=? AND role != 'Platform admin'"; args.append(airline_id)
    if ref:
        q += " AND ref=?"; args.append(ref)
    with _conn() as c:
        rows = c.execute(q + " ORDER BY id DESC LIMIT ?", (*args, limit)).fetchall()
    return [dict(r) for r in rows]


def count_events_all(action, since) -> int:
    """Across the whole platform (used for global limits, such as emails sent)."""
    with _conn() as c:
        return c.execute("SELECT COUNT(*) FROM events WHERE action=? AND ts>=?", (action, since)).fetchone()[0]


def count_events(airline_id, action, since, role=None) -> int:
    q, args = "SELECT COUNT(*) FROM events WHERE airline_id=? AND action=? AND ts>=?", [airline_id, action, since]
    if role:
        q += " AND role=?"; args.append(role)
    with _conn() as c:
        return c.execute(q, args).fetchone()[0]


def adopt_orphans(airline_id):
    """Older database files have complaints without an airline; give them to the demo airline."""
    with _conn() as c:
        c.execute("UPDATE complaints SET airline_id=? WHERE airline_id IS NULL", (airline_id,))
        c.execute("UPDATE events SET airline_id=? WHERE airline_id IS NULL AND role NOT IN ('Platform admin')", (airline_id,))


# ---------- conversation with the customer ----------
MAX_FOLLOWUPS = 5


def add_message(airline_id, complaint_id, sender, text, by="", ts=None):
    """sender is 'customer' or 'staff'. Staff messages are only added when a person approved the reply."""
    with _conn() as c:
        c.execute("INSERT INTO messages (airline_id, complaint_id, ts, sender, text, by) VALUES (?,?,?,?,?,?)",
                  (airline_id, complaint_id, ts or time.time(), sender, text, by))


def messages(airline_id, complaint_id):
    with _conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM messages WHERE airline_id=? AND complaint_id=? ORDER BY id", (airline_id, complaint_id))]


def reopen(airline_id, item_id, text, category=None, urgency=None, why=None) -> bool:
    """A customer replies to an answered complaint: keep the conversation, put it back in the queue.
    Only works while the complaint is Approved and under the follow-up limit. Returns False otherwise."""
    with _conn() as c:
        r = c.execute("SELECT * FROM complaints WHERE id=? AND airline_id=? AND status='Approved'", (item_id, airline_id)).fetchone()
        if not r or (r["followups"] or 0) >= MAX_FOLLOWUPS:
            return False
        have_staff = c.execute("SELECT 1 FROM messages WHERE complaint_id=? AND sender='staff'", (item_id,)).fetchone()
        if not have_staff and r["final_reply"]:  # the first reply predates the conversation log: keep it in the thread
            c.execute("INSERT INTO messages (airline_id, complaint_id, ts, sender, text, by) VALUES (?,?,?,?,?,?)",
                      (airline_id, item_id, r["resolved"] or r["created"], "staff", r["final_reply"], r["approved_by"] or ""))
        c.execute("INSERT INTO messages (airline_id, complaint_id, ts, sender, text, by) VALUES (?,?,?,?,?,?)",
                  (airline_id, item_id, time.time(), "customer", text, ""))
        data = json.loads(r["data"])
        if category == "High" and data.get("category") != "High":  # the follow-up shows it is more urgent than it looked
            data.update(category="High", urgency="High", urgency_why=why or "The customer's follow-up sounds urgent")
        cur = c.execute("UPDATE complaints SET status='New', note=NULL, ai=NULL, followups=COALESCE(followups,0)+1, data=? WHERE id=? AND airline_id=? AND status='Approved'",
                        (json.dumps(data), item_id, airline_id))
        return cur.rowcount == 1
