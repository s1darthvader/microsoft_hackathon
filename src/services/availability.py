"""Availability: the one implementation of the section 3 formula (BR-03, BR-19).

available = 0 if flagged unavailable, else capacity - sum(qty over COUNTED orders).
"""
from core.db import read
from core.rules import COUNTED

_COUNTED_SQL = ",".join(f"'{s}'" for s in COUNTED)  # constants, not user input

_ITEM_SQL = f"""
SELECT m.id AS item_id, m.outlet_id, m.name, m.category,
       a.slot_id, a.capacity, a.is_unavailable, a.unavailable_reason,
       COALESCE((SELECT SUM(l.quantity)
                   FROM order_line l JOIN orders o ON o.id = l.order_id
                  WHERE o.slot_id = a.slot_id AND l.item_id = a.item_id
                    AND o.status IN ({_COUNTED_SQL})), 0) AS counted
  FROM slot_item_availability a JOIN menu_item m ON m.id = a.item_id
"""


def _shape(row) -> dict:
    flagged = bool(row["is_unavailable"])
    available = 0 if flagged else max(row["capacity"] - row["counted"], 0)
    if flagged:
        state = "unavailable"
    else:
        state = "sold_out" if available == 0 else "available"
    return {
        "item_id": row["item_id"],
        "outlet_id": row["outlet_id"],
        "name": row["name"],
        "category": row["category"],
        "slot_id": row["slot_id"],
        "capacity": row["capacity"],
        "counted": row["counted"],
        "available": available,
        "state": state,  # available | sold_out | unavailable
        "reason": row["unavailable_reason"] if flagged else None,
    }


def slot_item(conn, slot_id, item_id):
    """One item in one slot, or None. Usable inside a caller's transaction."""
    row = conn.execute(
        _ITEM_SQL + " WHERE a.slot_id = ? AND a.item_id = ?", (slot_id, item_id)).fetchone()
    return _shape(row) if row else None


def slot_items(conn, slot_id, outlet_id=None) -> list:
    sql = _ITEM_SQL + " WHERE a.slot_id = ?"
    params = [slot_id]
    if outlet_id is not None:
        sql += " AND m.outlet_id = ?"
        params.append(outlet_id)
    return [_shape(r) for r in conn.execute(sql + " ORDER BY m.id", params).fetchall()]


def counted(conn, slot_id, item_id) -> int:
    row = slot_item(conn, slot_id, item_id)
    return row["counted"] if row else 0


def get_availability(outlet_id, slot_id) -> list:
    """Menu display for one outlet and slot (FR-C1)."""
    with read() as conn:
        return slot_items(conn, slot_id, outlet_id)


def slot_demand(outlet_id=None, date=None) -> list:
    """Capacity vs counted per outlet, slot and item (FR-M3, FR-A1)."""
    with read() as conn:
        outlets = {r["id"]: r["name"] for r in conn.execute("SELECT id, name FROM outlet")}
        sql, params = "SELECT * FROM pickup_slot", []
        if date:
            sql += " WHERE date = ?"
            params.append(date)
        rows = []
        for slot in conn.execute(sql + " ORDER BY date, start_time", params).fetchall():
            for item in slot_items(conn, slot["id"], outlet_id):
                rows.append({
                    "outlet": outlets[item["outlet_id"]],
                    "date": slot["date"],
                    "slot": f"{slot['start_time']}–{slot['end_time']}",
                    "item": item["name"],
                    "capacity": item["capacity"],
                    "counted": item["counted"],
                    "available": item["available"],
                    "state": item["state"],
                })
        return rows
