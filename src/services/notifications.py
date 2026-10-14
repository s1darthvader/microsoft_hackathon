"""In-app notifications (spec section 12, bonus).

Rows are written inside the caller transaction, so a notification exists if and
only if the change it describes was committed. Recipients are plain strings:
"customer:<campus id>" and "outlet:<outlet id>".
"""
from core.db import read, tx
from core.rules import CANCELLED, COLLECTED, CONFIRMED, CUSTOMER, PREPARING, READY, REJECTED
from services import clock


def customer_key(customer_id: str) -> str:
    return f"customer:{customer_id.strip().lower()}"


def outlet_key(outlet_id: int) -> str:
    return f"outlet:{outlet_id}"


def notify(conn, recipient: str, order_id, message: str) -> None:
    conn.execute(
        "INSERT INTO notification (recipient, order_id, message, created_at) VALUES (?, ?, ?, ?)",
        (recipient, order_id, message, clock.now_str(conn)))


def _outlet_name(conn, outlet_id) -> str:
    return conn.execute("SELECT name FROM outlet WHERE id = ?", (outlet_id,)).fetchone()["name"]


def on_transition(conn, order, to_status, actor, reason=None) -> None:
    """Tell the customer (and the outlet, for customer actions) about a status change."""
    oid = order["id"]
    mine = customer_key(order["customer_id"])
    if to_status == CONFIRMED:
        notify(conn, mine, oid, f"Order #{oid} is confirmed for {clock.slot_label(order)}.")
    elif to_status == PREPARING:
        notify(conn, mine, oid, f"Order #{oid} is being prepared.")
    elif to_status == READY:
        notify(conn, mine, oid, f"Order #{oid} is Ready for pickup at {clock.slot_label(order)}.")
    elif to_status == COLLECTED:
        notify(conn, mine, oid, f"Order #{oid} was collected. Enjoy your meal.")
    elif to_status == REJECTED:
        notify(conn, mine, oid, f"Pre-order #{oid} was rejected: {reason}.")
    elif to_status == CANCELLED:
        if actor == CUSTOMER:
            notify(conn, outlet_key(order["outlet_id"]), oid,
                   f"Order #{oid} was cancelled by the customer.")
        else:
            name = _outlet_name(conn, order["outlet_id"])
            notify(conn, mine, oid, f"Order #{oid} was cancelled by {name}: {reason}.")


def on_review_needed(conn, order_id, outlet_id, review_reason) -> None:
    notify(conn, outlet_key(outlet_id), order_id,
           f"New pre-order #{order_id} needs review ({review_reason.lower()}).")


def on_flag(conn, outlet_id, item_name, affected) -> None:
    notify(conn, outlet_key(outlet_id), None,
           f"{item_name} flagged unavailable. {affected} order(s) affected.")


def inbox(recipient: str, limit: int = 50) -> list:
    with read() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id, order_id, message, created_at, is_read FROM notification "
            "WHERE recipient = ? ORDER BY id DESC LIMIT ?", (recipient, limit))]


def unread_count(recipient: str) -> int:
    with read() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM notification WHERE recipient = ? AND is_read = 0",
            (recipient,)).fetchone()[0]


def mark_all_read(recipient: str) -> None:
    with tx() as conn:
        conn.execute("UPDATE notification SET is_read = 1 WHERE recipient = ?", (recipient,))
