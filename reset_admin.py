"""Recovery: set a new temporary password for a platform admin who is locked out.
Run on the machine that holds the database:   python reset_admin.py admin.demo
It prints a one-time password; the person must choose their own at the next sign-in."""
import sys

import auth, storage

if len(sys.argv) != 2:
    sys.exit("Usage: python reset_admin.py <platform admin username>")
u = storage.user_by_username(sys.argv[1])
if not u or u["role"] != auth.PLATFORM_ADMIN:
    sys.exit("No platform admin with that username.")
temp = auth.temp_password()
storage.set_password(u["id"], auth.hash_password(temp), True)
storage.set_user_active(u["id"], True)
storage.log(None, "recovery script", "", "password_reset", "", f"{u['name']} ({u['username']})")
print(f"Temporary password for {u['username']}: {temp}")
