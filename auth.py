"""Sign-in. Passwords are stored as salted PBKDF2 hashes (a different random salt per person), never in plain text.
Accounts live in the database (see storage.py). Admins create accounts with a temporary password that must be changed at first sign-in."""
import hashlib, hmac, secrets, time

import storage

DEMO_PASSWORD = "ExampleAir-2026"  # published in the README (assumption A8); only the demo accounts use it
PLATFORM_ADMIN, ORG_ADMIN, LEAD, AGENT = "Platform admin", "Airline admin", "Team lead", "Support agent"
STAFF_ROLES = (AGENT, LEAD, ORG_ADMIN)  # roles an airline admin can create
MAX_TRIES, LOCK_SECONDS = 5, 60
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"


def _hash(pw: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000).hex()


def hash_password(pw: str) -> str:
    salt = secrets.token_hex(8)
    return f"{salt}${_hash(pw, salt)}"


def verify(pw: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        return False
    return hmac.compare_digest(_hash(pw or "", salt), digest)


_DUMMY = hash_password("x")


def temp_password() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(12))


def weak_password(pw: str, current: str = None, username: str = None):
    """Returns a reason the password is not acceptable, or None."""
    if len(pw or "") < 10:
        return "Use at least 10 characters."
    if pw == DEMO_PASSWORD:
        return "Choose a password that is not the demo password."
    if current is not None and pw == current:
        return "Choose a password that is different from your current one."
    if username and username.lower() in pw.lower():
        return "Your password should not contain your username."
    if len(set(pw)) < 4:
        return "Use a more varied password."
    return None


TEMP_DAYS = 7  # an unused temporary password stops working after this long; an admin can send a new one


def temp_expired(u, now=None) -> bool:
    return bool(u and u.get("must_change") and u.get("created_by") != "setup"
                and (time.time() if now is None else now) - (u.get("pw_set") or u.get("created") or 0) > TEMP_DAYS * 86400)


def is_locked(u, now=None) -> bool:
    return bool(u) and (u.get("locked_until") or 0) > (time.time() if now is None else now)


def check(username: str, password: str):
    """The account if the sign-in is right and the account is active, else None. Timing does not reveal which part was wrong."""
    u = storage.user_by_username(username)
    ok = verify(password, u["pw"] if u else _DUMMY) and u is not None
    return u if ok and u["active"] and not is_locked(u) and not temp_expired(u) else None


def locked_for(failures: int, last_fail: float, now=None) -> int:
    """Seconds left on the lock (0 if not locked). AC8.4."""
    now = time.time() if now is None else now
    if failures < MAX_TRIES:
        return 0
    return max(0, int(LOCK_SECONDS - (now - last_fail)))
