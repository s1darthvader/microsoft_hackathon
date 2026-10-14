"""Sign-in for every stakeholder: one account per person, role and outlet come from the account."""
from core.db import read
from core.passwords import verify

_USER_SQL = (
    "SELECT u.id, u.username, u.password_hash, u.salt, u.role, u.display_name, u.campus_id, "
    "u.outlet_id, o.name AS outlet_name FROM app_user u LEFT JOIN outlet o ON o.id = u.outlet_id"
)


def _public(row) -> dict:
    user = dict(row)
    user.pop("password_hash", None)
    user.pop("salt", None)
    return user


def authenticate(username, password):
    """The signed-in user as a dict, or None for an unknown user or wrong password."""
    username = (username or "").strip().lower()
    if not username or not password:
        return None
    with read() as conn:
        row = conn.execute(_USER_SQL + " WHERE LOWER(u.username) = ?", (username,)).fetchone()
    if row is None or not verify(password, row["salt"], row["password_hash"]):
        return None
    return _public(row)


def get_user(user_id):
    """Re-read a signed-in user (e.g. after a reset); None if the account is gone."""
    with read() as conn:
        row = conn.execute(_USER_SQL + " WHERE u.id = ?", (user_id,)).fetchone()
    return _public(row) if row else None


def list_demo_accounts() -> list:
    """Usernames and roles for the login screen hint."""
    with read() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT u.username, u.role, COALESCE(o.name, '') AS outlet FROM app_user u "
            "LEFT JOIN outlet o ON o.id = u.outlet_id ORDER BY u.id")]
