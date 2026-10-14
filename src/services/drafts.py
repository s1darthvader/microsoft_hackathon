"""Per-user drafts: half-finished input (cart, typed reasons) kept across sign-out and refresh."""
import json

from core.db import read, tx
from services import clock


def load(user_id, key, default=None):
    with read() as conn:
        row = conn.execute(
            "SELECT value FROM draft WHERE user_id = ? AND key = ?", (user_id, key)).fetchone()
    return json.loads(row["value"]) if row else default


def load_prefix(user_id, prefix) -> dict:
    """All drafts whose key starts with `prefix`, as {key: value}."""
    with read() as conn:
        rows = conn.execute(
            "SELECT key, value FROM draft WHERE user_id = ? AND key LIKE ? ESCAPE '\\'",
            (user_id, _like(prefix))).fetchall()
    return {r["key"]: json.loads(r["value"]) for r in rows}


def save(user_id, key, value) -> None:
    with tx() as conn:
        conn.execute(
            "INSERT INTO draft (user_id, key, value, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value, "
            "updated_at = excluded.updated_at",
            (user_id, key, json.dumps(value), clock.now_str(conn)))


def clear(user_id, key) -> None:
    with tx() as conn:
        conn.execute("DELETE FROM draft WHERE user_id = ? AND key = ?", (user_id, key))


def clear_prefix(user_id, prefix) -> None:
    with tx() as conn:
        conn.execute(
            "DELETE FROM draft WHERE user_id = ? AND key LIKE ? ESCAPE '\\'",
            (user_id, _like(prefix)))


def _like(prefix: str) -> str:
    escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return escaped + "%"
