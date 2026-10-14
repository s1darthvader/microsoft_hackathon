"""Next available slot suggestions (spec section 12, alternative bonus).

Suggestions are advice only: the customer picks one, and booking it re-runs the
full ordering.submit_order validation. Nothing here reserves stock (BR-22).
"""
from core.db import read
from core.rules import BusinessRuleError
from services import availability, clock, ordering


def _fits(conn, slot_id, cart, outlet_id) -> bool:
    for item_id, quantity in cart.items():
        row = availability.slot_item(conn, slot_id, item_id)
        if (row is None or row["outlet_id"] != outlet_id
                or row["state"] != "available" or quantity > row["available"]):
            return False
    return True


def next_available_slots(outlet_id, slot_id, lines, limit=3) -> list:
    """Later slots at the same outlet where the whole order fits.

    Returns [] when the cart is invalid, or when the requested slot would
    have accepted it (so the refusal was not about the slot).
    """
    try:
        cart = ordering.normalise_lines(lines)
    except BusinessRuleError:
        return []
    with read() as conn:
        slot = conn.execute("SELECT * FROM pickup_slot WHERE id = ?", (slot_id,)).fetchone()
        if slot is None:
            return []
        now = clock.get_now(conn)
        requested_start = clock.slot_start(slot)
        if now < requested_start and _fits(conn, slot_id, cart, outlet_id):
            return []
        after = max(now, requested_start)
        found = []
        for candidate in conn.execute("SELECT * FROM pickup_slot ORDER BY date, start_time"):
            if clock.slot_start(candidate) <= after:
                continue
            if _fits(conn, candidate["id"], cart, outlet_id):
                found.append({
                    "slot_id": candidate["id"],
                    "date": candidate["date"],
                    "label": clock.slot_label(candidate),
                })
                if len(found) == limit:
                    break
        return found
