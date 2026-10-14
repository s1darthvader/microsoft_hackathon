"""Read models for the UI: outlets, slots, orders with timeline and derived flags."""
from core.db import read
from core.rules import CONFIRMED, PENDING
from services import clock, lifecycle


def list_outlets() -> list:
    with read() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM outlet ORDER BY id")]


def list_dates() -> list:
    with read() as conn:
        return [r["date"] for r in conn.execute("SELECT DISTINCT date FROM pickup_slot ORDER BY date")]


def list_slots(date=None) -> list:
    sql, params = "SELECT * FROM pickup_slot", []
    if date:
        sql += " WHERE date = ?"
        params.append(date)
    with read() as conn:
        return [dict(r) for r in conn.execute(sql + " ORDER BY date, start_time", params)]


def list_orders(customer_id=None, outlet_id=None, status=None, order_id=None, viewer=None) -> list:
    """Orders with lines, history and derived flags.

    `viewer` is an actor name; when given, each order carries `allowed_actions`.
    The pickup code is deliberately not returned (A4): the customer sees it once, at submit.
    """
    where, params = [], []
    if customer_id:
        where.append("LOWER(o.customer_id) = LOWER(?)")
        params.append(customer_id.strip())
    if outlet_id is not None:
        where.append("o.outlet_id = ?")
        params.append(outlet_id)
    if status:
        where.append("o.status = ?")
        params.append(status)
    if order_id is not None:
        where.append("o.id = ?")
        params.append(order_id)
    sql = (
        "SELECT o.id, o.outlet_id, ou.name AS outlet_name, o.slot_id, s.date, s.start_time, "
        "s.end_time, o.customer_id, o.customer_name, o.status, o.review_reason, "
        "o.closure_reason, o.created_at "
        "FROM orders o JOIN outlet ou ON ou.id = o.outlet_id JOIN pickup_slot s ON s.id = o.slot_id"
    )
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY s.date, s.start_time, o.id"

    with read() as conn:
        now = clock.get_now(conn)
        orders = []
        for row in conn.execute(sql, params).fetchall():
            o = dict(row)
            o["slot_label"] = clock.slot_label(o)
            o["lines"] = [dict(r) for r in conn.execute(
                "SELECT l.item_id, m.name, l.quantity FROM order_line l "
                "JOIN menu_item m ON m.id = l.item_id WHERE l.order_id = ? ORDER BY m.id", (o["id"],))]
            o["history"] = [dict(r) for r in conn.execute(
                "SELECT from_status, to_status, actor, reason, timestamp FROM order_status_history "
                "WHERE order_id = ? ORDER BY id", (o["id"],))]
            flagged = []
            if o["status"] in (PENDING, CONFIRMED):
                flagged = [f"{r['name']} ({r['unavailable_reason']})" for r in conn.execute(
                    "SELECT m.name, a.unavailable_reason FROM order_line l "
                    "JOIN slot_item_availability a ON a.item_id = l.item_id AND a.slot_id = ? "
                    "JOIN menu_item m ON m.id = l.item_id "
                    "WHERE l.order_id = ? AND a.is_unavailable = 1", (o["slot_id"], o["id"]))]
            o["flagged_items"] = flagged
            o["affected"] = bool(flagged)
            o["needs_review"] = o["status"] == PENDING and o["review_reason"] is not None
            o["overdue"] = o["status"] == PENDING and now >= clock.slot_end(o)
            if viewer:
                o["allowed_actions"] = lifecycle.allowed_actions(o["status"], viewer)
            orders.append(o)
        return orders


def get_order(order_id, viewer=None):
    found = list_orders(order_id=order_id, viewer=viewer)
    return found[0] if found else None


def list_items(outlet_id) -> list:
    with read() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id AS item_id, name, category FROM menu_item WHERE outlet_id = ? ORDER BY id",
            (outlet_id,))]
