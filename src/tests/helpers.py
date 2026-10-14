"""Lookups by name so tests read like the acceptance scenarios."""
from core.db import read
from services import availability, lifecycle, menu, ordering, queries

D4, D5 = "2026-08-04", "2026-08-05"
MAIN, KIOSK = "Main Canteen", "Snack Kiosk"


def outlet_id(name):
    with read() as conn:
        return conn.execute("SELECT id FROM outlet WHERE name = ?", (name,)).fetchone()["id"]


def item_id(name):
    with read() as conn:
        return conn.execute("SELECT id FROM menu_item WHERE name = ?", (name,)).fetchone()["id"]


def slot_id(date, start):
    with read() as conn:
        return conn.execute(
            "SELECT id FROM pickup_slot WHERE date = ? AND start_time = ?", (date, start)).fetchone()["id"]


def place(outlet, start, lines, date=D4, customer="S101", name="Asha"):
    """Submit a pre-order. `lines` maps item name to quantity."""
    cart = [{"item_id": item_id(n), "quantity": q} for n, q in lines.items()]
    return ordering.submit_order(outlet_id(outlet), slot_id(date, start), customer, name, cart)


def stock(outlet, start, item, date=D4):
    """The availability row for one item in one slot."""
    rows = availability.get_availability(outlet_id(outlet), slot_id(date, start))
    return next(r for r in rows if r["name"] == item)


def available(outlet, start, item, date=D4):
    return stock(outlet, start, item, date)["available"]


def status(order_id):
    return queries.get_order(order_id)["status"]


def history(order_id):
    return [(h["from_status"], h["to_status"], h["actor"]) for h in queries.get_order(order_id)["history"]]


def set_policy(outlet, auto_confirm, threshold=10):
    menu.set_outlet_policy(outlet_id(outlet), auto_confirm, threshold)


def flag(item, reason, outlet=MAIN, date=D4, start=None):
    sid = slot_id(date, start) if start else None
    return menu.set_unavailable(outlet_id(outlet), item_id(item), date, sid, True, reason)


def act(order_id, action, actor, **kwargs):
    return lifecycle.transition(order_id, action, actor, **kwargs)
