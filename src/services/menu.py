"""Manager actions: availability flags, confirmation policy, capacity (BR-17, BR-18, BR-20)."""
from core.db import tx
from core.rules import BusinessRuleError, CONFIRMED, PENDING, UNAVAILABLE_REASONS
from services import availability, notifications


def set_unavailable(outlet_id, item_id, date, slot_id=None, flagged=True, reason=None) -> int:
    """Flag or unflag an item for one slot, or every slot on `date` when slot_id is None.

    Returns how many existing Pending/Confirmed orders the flag affects. Existing
    orders are never changed automatically (A8); staff decide (BR-18).
    """
    if flagged:
        if not (reason or "").strip():
            raise BusinessRuleError("A reason is required.")
        if reason not in UNAVAILABLE_REASONS:
            raise BusinessRuleError("Choose one of: " + ", ".join(UNAVAILABLE_REASONS) + ".")
    with tx() as conn:
        item = conn.execute(
            "SELECT id, name FROM menu_item WHERE id = ? AND outlet_id = ?", (item_id, outlet_id)).fetchone()
        if item is None:
            raise BusinessRuleError("That item does not belong to this outlet.")
        sql, params = "SELECT id FROM pickup_slot WHERE date = ?", [date]
        if slot_id is not None:
            sql += " AND id = ?"
            params.append(slot_id)
        slot_ids = [r["id"] for r in conn.execute(sql, params).fetchall()]
        if not slot_ids:
            raise BusinessRuleError("No pickup slots match that date.")
        marks = ",".join("?" * len(slot_ids))
        conn.execute(
            "UPDATE slot_item_availability SET is_unavailable = ?, unavailable_reason = ? "
            f"WHERE item_id = ? AND slot_id IN ({marks})",
            (1 if flagged else 0, reason if flagged else None, item_id, *slot_ids))
        if not flagged:
            return 0
        affected = conn.execute(
            "SELECT COUNT(DISTINCT o.id) FROM orders o JOIN order_line l ON l.order_id = o.id "
            f"WHERE l.item_id = ? AND o.slot_id IN ({marks}) AND o.status IN (?, ?)",
            (item_id, *slot_ids, PENDING, CONFIRMED)).fetchone()[0]
        notifications.on_flag(conn, outlet_id, item["name"], affected)
        return affected


def set_outlet_policy(outlet_id, auto_confirm, bulk_threshold) -> None:
    """FR-M2: auto-confirm on/off and the bulk-review threshold."""
    if not isinstance(bulk_threshold, int) or bulk_threshold < 1:
        raise BusinessRuleError("The bulk threshold must be a whole number of 1 or more.")
    with tx() as conn:
        cur = conn.execute(
            "UPDATE outlet SET auto_confirm = ?, bulk_review_threshold = ? WHERE id = ?",
            (1 if auto_confirm else 0, bulk_threshold, outlet_id))
        if cur.rowcount == 0:
            raise BusinessRuleError("Unknown outlet.")


def set_capacity(outlet_id, slot_id, item_id, new_capacity) -> None:
    """FR-M4 / BR-20 / V-13: never below the quantity already counted."""
    if not isinstance(new_capacity, int) or new_capacity < 0:
        raise BusinessRuleError("Capacity must be a whole number of 0 or more.")
    with tx() as conn:
        row = availability.slot_item(conn, slot_id, item_id)
        if row is None or row["outlet_id"] != outlet_id:
            raise BusinessRuleError("That item is not on the menu of this outlet for this slot.")
        if new_capacity < row["counted"]:
            raise BusinessRuleError(
                f"Cannot set capacity to {new_capacity}: {row['counted']} units are already "
                "counted for this slot.")
        conn.execute(
            "UPDATE slot_item_availability SET capacity = ? WHERE slot_id = ? AND item_id = ?",
            (new_capacity, slot_id, item_id))
