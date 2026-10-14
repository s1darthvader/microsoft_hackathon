"""Submit a pre-order: validate every line, reserve atomically, auto-confirm (BR-01 .. BR-09)."""
import secrets

from core.db import tx
from core.rules import BusinessRuleError, CUSTOMER, PENDING, SYSTEM
from services import availability, clock, lifecycle, notifications

_NEED_QTY = "Add at least one item with a whole-number quantity of 1 or more."


def _whole_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def normalise_lines(lines) -> dict:
    """V-02: merge duplicate items and require whole-number quantities >= 1."""
    cart = {}
    for line in lines or []:
        quantity = _whole_number(line.get("quantity"))
        if quantity is None or quantity < 1:
            raise BusinessRuleError(_NEED_QTY)
        cart[line["item_id"]] = cart.get(line["item_id"], 0) + quantity
    if not cart:
        raise BusinessRuleError(_NEED_QTY)
    return cart


def _check_one_outlet(conn, outlet, cart) -> None:
    """BR-02 / V-03."""
    for item_id in cart:
        item = conn.execute(
            "SELECT m.name, m.outlet_id, o.name AS outlet_name FROM menu_item m "
            "JOIN outlet o ON o.id = m.outlet_id WHERE m.id = ?", (item_id,)).fetchone()
        if item is None:
            raise BusinessRuleError("One of the selected items does not exist.")
        if item["outlet_id"] != outlet["id"]:
            raise BusinessRuleError(
                f"{item['name']} is sold by {item['outlet_name']}. "
                "A pre-order can include items from one outlet only.")


def _check_availability(conn, slot, cart) -> None:
    """V-05 / V-06 / V-07: check every line before failing, list all failures."""
    when = clock.slot_label(slot)
    failures = []
    for item_id, quantity in cart.items():
        row = availability.slot_item(conn, slot["id"], item_id)
        if row["state"] == "unavailable":
            failures.append(
                f"{row['name']} is unavailable for {when} on {clock.long_date(slot['date'])} "
                f"({row['reason']}).")
        elif row["state"] == "sold_out":
            failures.append(f"{row['name']} is sold out for {when}.")
        elif quantity > row["available"]:
            failures.append(
                f"{row['name']}: you asked for {quantity}, only {row['available']} are "
                f"available for {when}.")
    if failures:
        raise BusinessRuleError(
            "Your pre-order was not placed. Nothing has been reserved.", lines=failures)


def submit_order(outlet_id, slot_id, customer_id, customer_name, lines, payment_ref=None) -> dict:
    """Place a pre-order. All lines are reserved together or not at all (BR-04, BR-05).

    `lines` is a list of {"item_id": int, "quantity": int}. Returns the order id,
    its pickup code, its status, the review reason (None when auto-confirmed) and the total.
    `payment_ref` is the demo checkout reference; no money moves (A10).
    """
    customer_id = (customer_id or "").strip()
    customer_name = (customer_name or "").strip()
    if not customer_id or not customer_name:
        raise BusinessRuleError("Please enter your campus ID and name.")
    cart = normalise_lines(lines)

    with tx() as conn:
        outlet = conn.execute("SELECT * FROM outlet WHERE id = ?", (outlet_id,)).fetchone()
        slot = conn.execute("SELECT * FROM pickup_slot WHERE id = ?", (slot_id,)).fetchone()
        if outlet is None or slot is None:
            raise BusinessRuleError("Choose an outlet and a pickup slot.")
        _check_one_outlet(conn, outlet, cart)
        if clock.get_now(conn) >= clock.slot_start(slot):
            raise BusinessRuleError(
                f"The {clock.slot_label(slot)} slot has already started. Choose a later slot.")
        _check_availability(conn, slot, cart)

        cur = conn.execute(
            "INSERT INTO orders (outlet_id, slot_id, customer_id, customer_name, status, "
            "pickup_code, payment_ref, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (outlet_id, slot_id, customer_id, customer_name, PENDING,
             f"{secrets.randbelow(10000):04d}", payment_ref, clock.now_str(conn)))
        order_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO order_line (order_id, item_id, quantity) VALUES (?, ?, ?)",
            [(order_id, item_id, qty) for item_id, qty in cart.items()])
        lifecycle.record_history(conn, order_id, None, PENDING, CUSTOMER)

        review_reason = None
        if outlet["auto_confirm"] and sum(cart.values()) <= outlet["bulk_review_threshold"]:
            lifecycle.apply_transition(conn, order_id, "auto_confirm", SYSTEM)  # BR-08
        else:
            review_reason = "Bulk order" if outlet["auto_confirm"] else "Manual confirmation"  # BR-09
            conn.execute("UPDATE orders SET review_reason = ? WHERE id = ?", (review_reason, order_id))
            notifications.on_review_needed(conn, order_id, outlet_id, review_reason)

        row = conn.execute(
            "SELECT status, pickup_code FROM orders WHERE id = ?", (order_id,)).fetchone()
        total = conn.execute(
            "SELECT COALESCE(SUM(l.quantity * m.price), 0) FROM order_line l "
            "JOIN menu_item m ON m.id = l.item_id WHERE l.order_id = ?", (order_id,)).fetchone()[0]
        return {
            "order_id": order_id,
            "pickup_code": row["pickup_code"],
            "status": row["status"],
            "review_reason": review_reason,
            "payment_ref": payment_ref,
            "total": total,
        }
