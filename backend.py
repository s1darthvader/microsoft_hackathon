import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

# Optional FastAPI wrapper (runs if fastapi/pydantic are installed)
try:
    from fastapi import FastAPI, HTTPException, Query
    from pydantic import BaseModel
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

DB_PATH = "campus_food.db"
OPERATING_DATE = "2026-08-04"

VALID_TRANSITIONS = {
    "CONFIRMED": "PREPARING",
    "PREPARING": "READY_FOR_PICKUP",
    "READY_FOR_PICKUP": "COMPLETED",
}


@contextmanager
def get_db():
    """Context manager ensuring atomic transactions and row-dict access."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# =====================================================================
# 1. DATABASE INITIALIZATION & SEED DATA (4 AUGUST 2026)
# =====================================================================

def init_and_seed_db(force_reset: bool = False):
    """Creates tables and seeds the exact IIIT Hackathon initial dataset."""
    with get_db() as conn:
        cursor = conn.cursor()

        if force_reset:
            cursor.executescript("""
                DROP TABLE IF EXISTS order_items;
                DROP TABLE IF EXISTS orders;
                DROP TABLE IF EXISTS slot_inventory;
                DROP TABLE IF EXISTS pickup_slots;
                DROP TABLE IF EXISTS menu_items;
            """)

        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS menu_items (
                item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                category TEXT NOT NULL,
                default_slot_max INTEGER NOT NULL CHECK (default_slot_max > 0),
                is_globally_available INTEGER NOT NULL DEFAULT 1,
                unavailability_reason TEXT
            );

            CREATE TABLE IF NOT EXISTS pickup_slots (
                slot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                slot_date TEXT NOT NULL,
                time_window TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                UNIQUE(slot_date, time_window)
            );

            CREATE TABLE IF NOT EXISTS slot_inventory (
                inventory_id INTEGER PRIMARY KEY AUTOINCREMENT,
                slot_id INTEGER NOT NULL REFERENCES pickup_slots(slot_id),
                item_id INTEGER NOT NULL REFERENCES menu_items(item_id),
                max_qty INTEGER NOT NULL,
                committed_qty INTEGER NOT NULL DEFAULT 0,
                UNIQUE(slot_id, item_id),
                CHECK (committed_qty >= 0 AND committed_qty <= max_qty)
            );

            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                customer_name TEXT NOT NULL,
                slot_id INTEGER NOT NULL REFERENCES pickup_slots(slot_id),
                status TEXT NOT NULL CHECK (
                    status IN ('SUBMITTED', 'CONFIRMED', 'REJECTED', 'CANCELLED', 
                               'PREPARING', 'READY_FOR_PICKUP', 'COMPLETED')
                ),
                status_reason TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS order_items (
                order_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL REFERENCES orders(order_id),
                item_id INTEGER NOT NULL REFERENCES menu_items(item_id),
                quantity INTEGER NOT NULL CHECK (quantity > 0)
            );
        """)

        # Check if already seeded
        cursor.execute("SELECT COUNT(*) as cnt FROM menu_items")
        if cursor.fetchone()["cnt"] > 0:
            return

        # 1. Seed Menu Items
        items = [
            # (name, category, default_slot_max, is_globally_available, reason)
            ("Veg Sandwich", "Snacks", 20, 1, None),
            ("Masala Dosa", "South Indian", 15, 1, None),
            ("Paneer Rice Bowl", "Meals", 12, 1, None),
            ("Cold Coffee", "Beverages", 18, 0, "Temporarily unavailable for all pickup slots on 4 Aug 2026"),
            ("Fruit Bowl", "Healthy Meals", 10, 1, None),
        ]
        cursor.executemany("""
            INSERT INTO menu_items (name, category, default_slot_max, is_globally_available, unavailability_reason)
            VALUES (?, ?, ?, ?, ?)
        """, items)

        # 2. Seed Pickup Slots for 4 August 2026
        slots = [
            (OPERATING_DATE, "12:00-12:30", 1),
            (OPERATING_DATE, "12:30-13:00", 1),
            (OPERATING_DATE, "13:00-13:30", 1),
            (OPERATING_DATE, "13:30-14:00", 1),
        ]
        cursor.executemany("""
            INSERT INTO pickup_slots (slot_date, time_window, is_active)
            VALUES (?, ?, ?)
        """, slots)

        # Fetch IDs for mapping
        cursor.execute("SELECT item_id, name, default_slot_max FROM menu_items")
        item_map = {row["name"]: (row["item_id"], row["default_slot_max"]) for row in cursor.fetchall()}

        cursor.execute("SELECT slot_id, time_window FROM pickup_slots")
        slot_map = {row["time_window"]: row["slot_id"] for row in cursor.fetchall()}

        # 3. Initialize slot_inventory (0 committed by default)
        for window, s_id in slot_map.items():
            for name, (i_id, max_q) in item_map.items():
                cursor.execute("""
                    INSERT INTO slot_inventory (slot_id, item_id, max_qty, committed_qty)
                    VALUES (?, ?, ?, 0)
                """, (s_id, i_id, max_q))

        # 4. Seed Pre-Existing Committed Orders (matching problem statement)
        now_str = "2026-08-04 11:00:00"
        
        # Seed Order 1: 5 units of Paneer Rice Bowl in 12:30-13:00
        slot_1230 = slot_map["12:30-13:00"]
        paneer_id = item_map["Paneer Rice Bowl"][0]
        cursor.execute("""
            INSERT INTO orders (order_id, customer_name, slot_id, status, status_reason, created_at, updated_at)
            VALUES ('ORD-1001', 'Placement_Cell_Coord', ?, 'CONFIRMED', 'Initial seeded commitment', ?, ?)
        """, (slot_1230, now_str, now_str))
        cursor.execute("INSERT INTO order_items (order_id, item_id, quantity) VALUES ('ORD-1001', ?, 5)", (paneer_id,))
        cursor.execute("""
            UPDATE slot_inventory SET committed_qty = 5 WHERE slot_id = ? AND item_id = ?
        """, (slot_1230, paneer_id))

        # Seed Order 2: 8 units Veg Sandwich + 4 units Fruit Bowl in 13:00-13:30
        slot_1300 = slot_map["13:00-13:30"]
        sandwich_id = item_map["Veg Sandwich"][0]
        fruit_id = item_map["Fruit Bowl"][0]
        cursor.execute("""
            INSERT INTO orders (order_id, customer_name, slot_id, status, status_reason, created_at, updated_at)
            VALUES ('ORD-1002', 'Workshop_Batch_A', ?, 'CONFIRMED', 'Initial seeded commitment', ?, ?)
        """, (slot_1300, now_str, now_str))
        cursor.execute("INSERT INTO order_items (order_id, item_id, quantity) VALUES ('ORD-1002', ?, 8)", (sandwich_id,))
        cursor.execute("INSERT INTO order_items (order_id, item_id, quantity) VALUES ('ORD-1002', ?, 4)", (fruit_id,))
        cursor.execute("""
            UPDATE slot_inventory SET committed_qty = 8 WHERE slot_id = ? AND item_id = ?
        """, (slot_1300, sandwich_id))
        cursor.execute("""
            UPDATE slot_inventory SET committed_qty = 4 WHERE slot_id = ? AND item_id = ?
        """, (slot_1300, fruit_id))


# =====================================================================
# 2. SERVICE LAYER (CORE BUSINESS LOGIC & VALIDATIONS)
# =====================================================================

def get_pickup_slots() -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute("""
            SELECT slot_id, slot_date, time_window, is_active
            FROM pickup_slots
            ORDER BY slot_id
        """).fetchall()
        return [dict(r) for r in rows]


def get_menu_by_slot(slot_id: int) -> List[Dict[str, Any]]:
    """Returns menu items with real-time slot availability (Conditions 2, 3, 5)."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT 
                m.item_id,
                m.name,
                m.category,
                m.is_globally_available,
                m.unavailability_reason,
                si.slot_id,
                si.max_qty,
                si.committed_qty,
                CASE 
                    WHEN m.is_globally_available = 1 THEN (si.max_qty - si.committed_qty)
                    ELSE 0 
                END AS available_qty
            FROM menu_items m
            JOIN slot_inventory si ON m.item_id = si.item_id
            WHERE si.slot_id = ?
            ORDER BY m.item_id
        """, (slot_id,)).fetchall()
        return [dict(r) for r in rows]


def _find_alternative_slots(conn: sqlite3.Connection, requested_items: List[Dict[str, int]], exclude_slot_id: int) -> List[str]:
    """Bonus Feature: Finds other pickup slots on 4 Aug 2026 that can fulfill the exact cart."""
    slots = conn.execute("SELECT slot_id, time_window FROM pickup_slots WHERE slot_id != ? AND is_active = 1", (exclude_slot_id,)).fetchall()
    viable_windows = []

    for s in slots:
        s_id = s["slot_id"]
        can_fulfill = True
        for req in requested_items:
            row = conn.execute("""
                SELECT m.is_globally_available, (si.max_qty - si.committed_qty) AS avail
                FROM menu_items m
                JOIN slot_inventory si ON m.item_id = si.item_id
                WHERE si.slot_id = ? AND m.item_id = ?
            """, (s_id, req["item_id"])).fetchone()
            if not row or not row["is_globally_available"] or row["avail"] < req["quantity"]:
                can_fulfill = False
                break
        if can_fulfill:
            viable_windows.append(s["time_window"])
    return viable_windows


def submit_preorder(customer_name: str, slot_id: int, items: List[Dict[str, int]]) -> Dict[str, Any]:
    """
    Validates and submits a pre-order atomically (Conditions 1, 2, 3, 4, 5, 12).
    items format: [{"item_id": 1, "quantity": 2}, ...]
    """
    customer_name = customer_name.strip()
    if not customer_name:
        return {"success": False, "error": "Customer name/ID is required."}

    # Filter out 0-quantity items and merge duplicates if any
    merged_cart: Dict[int, int] = {}
    for entry in items:
        qty = int(entry.get("quantity", 0))
        if qty < 0:
            return {"success": False, "error": "Item quantity cannot be negative."}
        if qty > 0:
            i_id = int(entry["item_id"])
            merged_cart[i_id] = merged_cart.get(i_id, 0) + qty

    if not merged_cart:
        return {"success": False, "error": "Pre-order must contain at least one menu item with quantity > 0."}

    normalized_items = [{"item_id": k, "quantity": v} for k, v in merged_cart.items()]

    with get_db() as conn:
        # Verify slot exists
        slot_row = conn.execute("SELECT time_window, is_active FROM pickup_slots WHERE slot_id = ?", (slot_id,)).fetchone()
        if not slot_row or not slot_row["is_active"]:
            return {"success": False, "error": "Selected pickup slot is invalid or inactive."}

        failed_reasons = []

        # Atomic Validation Loop (All-or-Nothing - Conditions 3, 4, 5, 12)
        for req in normalized_items:
            row = conn.execute("""
                SELECT m.name, m.is_globally_available, m.unavailability_reason,
                       si.max_qty, si.committed_qty, (si.max_qty - si.committed_qty) AS avail
                FROM menu_items m
                JOIN slot_inventory si ON m.item_id = si.item_id
                WHERE si.slot_id = ? AND m.item_id = ?
            """, (slot_id, req["item_id"])).fetchone()

            if not row:
                failed_reasons.append(f"Item ID {req['item_id']} does not exist.")
            elif not row["is_globally_available"]:
                reason = row["unavailability_reason"] or "Temporarily unavailable"
                failed_reasons.append(f"'{row['name']}' is unavailable ({reason}).")
            elif req["quantity"] > row["avail"]:
                failed_reasons.append(
                    f"'{row['name']}': requested {req['quantity']}, but only {row['avail']} available in slot {slot_row['time_window']}."
                )

        if failed_reasons:
            alternatives = _find_alternative_slots(conn, normalized_items, slot_id)
            return {
                "success": False,
                "error": "Order blocked: Complete requested quantities cannot be fulfilled for the selected slot.",
                "failed_items": failed_reasons,
                "alternative_slots": alternatives,
            }

        # Generate readable Order ID
        count_row = conn.execute("SELECT COUNT(*) AS cnt FROM orders").fetchone()
        order_id = f"ORD-{1001 + count_row['cnt']}"
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. Insert Order in SUBMITTED state
        conn.execute("""
            INSERT INTO orders (order_id, customer_name, slot_id, status, status_reason, created_at, updated_at)
            VALUES (?, ?, ?, 'SUBMITTED', NULL, ?, ?)
        """, (order_id, customer_name, slot_id, now_str, now_str))

        # 2. Insert Line Items & Reserve Inventory Immediately (Condition 2)
        for req in normalized_items:
            conn.execute("""
                INSERT INTO order_items (order_id, item_id, quantity)
                VALUES (?, ?, ?)
            """, (order_id, req["item_id"], req["quantity"]))

            conn.execute("""
                UPDATE slot_inventory
                SET committed_qty = committed_qty + ?
                WHERE slot_id = ? AND item_id = ?
            """, (req["quantity"], slot_id, req["item_id"]))

        return {
            "success": True,
            "order_id": order_id,
            "status": "SUBMITTED",
            "slot_window": slot_row["time_window"],
            "message": f"Pre-order {order_id} submitted! Inventory reserved for {slot_row['time_window']}.",
        }


def get_orders(customer_name: Optional[str] = None, slot_id: Optional[int] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetches orders with nested line items for either Customer View or Staff Queue."""
    with get_db() as conn:
        query = """
            SELECT o.order_id, o.customer_name, o.slot_id, p.time_window, p.slot_date,
                   o.status, o.status_reason, o.created_at, o.updated_at
            FROM orders o
            JOIN pickup_slots p ON o.slot_id = p.slot_id
            WHERE 1=1
        """
        params: List[Any] = []
        if customer_name:
            query += " AND LOWER(o.customer_name) = LOWER(?)"
            params.append(customer_name.strip())
        if slot_id:
            query += " AND o.slot_id = ?"
            params.append(slot_id)
        if status:
            query += " AND o.status = ?"
            params.append(status)

        query += " ORDER BY o.created_at DESC, o.order_id DESC"
        orders = [dict(r) for r in conn.execute(query, params).fetchall()]

        for o in orders:
            items = conn.execute("""
                SELECT oi.item_id, m.name, m.category, oi.quantity, m.is_globally_available
                FROM order_items oi
                JOIN menu_items m ON oi.item_id = m.item_id
                WHERE oi.order_id = ?
            """, (o["order_id"],)).fetchall()
            o["items"] = [dict(i) for i in items]
            o["can_customer_cancel"] = o["status"] in ("SUBMITTED", "CONFIRMED")

        return orders


def _release_order_inventory(conn: sqlite3.Connection, order_id: str, slot_id: int):
    """Helper to release reserved quantities back to the pickup slot (Conditions 7 & 8)."""
    items = conn.execute("SELECT item_id, quantity FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
    for item in items:
        conn.execute("""
            UPDATE slot_inventory
            SET committed_qty = committed_qty - ?
            WHERE slot_id = ? AND item_id = ?
        """, (item["quantity"], slot_id, item["item_id"]))


def cancel_order(order_id: str, customer_name: Optional[str] = None, reason: str = "Cancelled by customer") -> Dict[str, Any]:
    """Cancels a SUBMITTED or CONFIRMED order and releases inventory (Conditions 8 & 9)."""
    with get_db() as conn:
        order = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
        if not order:
            return {"success": False, "error": f"Order {order_id} not found."}

        if customer_name and order["customer_name"].lower() != customer_name.strip().lower():
            return {"success": False, "error": "Unauthorized: Order belongs to a different customer."}

        current_status = order["status"]

        # Condition 9: Cannot cancel once preparation begins
        if current_status in ("PREPARING", "READY_FOR_PICKUP", "COMPLETED"):
            return {
                "success": False,
                "error": f"Cannot cancel order in '{current_status}' state. Preparation has already begun or completed.",
            }

        if current_status in ("CANCELLED", "REJECTED"):
            return {"success": False, "error": f"Order is already closed ({current_status})."}

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("""
            UPDATE orders
            SET status = 'CANCELLED', status_reason = ?, updated_at = ?
            WHERE order_id = ?
        """, (reason, now_str, order_id))

        _release_order_inventory(conn, order_id, order["slot_id"])

        return {
            "success": True,
            "order_id": order_id,
            "status": "CANCELLED",
            "message": f"Order {order_id} cancelled. Reserved quantities have been released back to the slot.",
        }


def confirm_preorder(order_id: str) -> Dict[str, Any]:
    """Staff confirms a SUBMITTED pre-order (Condition 6)."""
    with get_db() as conn:
        order = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
        if not order:
            return {"success": False, "error": f"Order {order_id} not found."}

        if order["status"] != "SUBMITTED":
            return {"success": False, "error": f"Only SUBMITTED orders can be confirmed (current: {order['status']})."}

        # Check if any item in the order was marked globally unavailable after submission
        unavailable_items = conn.execute("""
            SELECT m.name, m.unavailability_reason
            FROM order_items oi
            JOIN menu_items m ON oi.item_id = m.item_id
            WHERE oi.order_id = ? AND m.is_globally_available = 0
        """, (order_id,)).fetchall()

        if unavailable_items:
            names = ", ".join(r["name"] for r in unavailable_items)
            return {
                "success": False,
                "error": f"Cannot confirm: [{names}] became temporarily unavailable. Please reject this pre-order.",
            }

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("""
            UPDATE orders SET status = 'CONFIRMED', updated_at = ? WHERE order_id = ?
        """, (now_str, order_id))

        return {"success": True, "order_id": order_id, "status": "CONFIRMED", "message": f"Order {order_id} confirmed."}


def reject_preorder(order_id: str, reason: str = "Rejected by outlet staff") -> Dict[str, Any]:
    """Staff rejects a SUBMITTED pre-order (or emergency-rejects CONFIRMED) and releases inventory (Condition 7)."""
    with get_db() as conn:
        order = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
        if not order:
            return {"success": False, "error": f"Order {order_id} not found."}

        if order["status"] not in ("SUBMITTED", "CONFIRMED"):
            return {
                "success": False,
                "error": f"Cannot reject order in '{order['status']}' state. Only SUBMITTED or pre-prep CONFIRMED orders can be rejected.",
            }

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("""
            UPDATE orders
            SET status = 'REJECTED', status_reason = ?, updated_at = ?
            WHERE order_id = ?
        """, (reason or "Rejected by staff", now_str, order_id))

        _release_order_inventory(conn, order_id, order["slot_id"])

        return {
            "success": True,
            "order_id": order_id,
            "status": "REJECTED",
            "message": f"Order {order_id} rejected and closed. Reserved item quantities released.",
        }


def advance_order_stage(order_id: str) -> Dict[str, Any]:
    """
    Advances a CONFIRMED order through PREPARING -> READY_FOR_PICKUP -> COMPLETED (Conditions 10 & 11).
    Prevents double collection once COMPLETED.
    """
    with get_db() as conn:
        order = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
        if not order:
            return {"success": False, "error": f"Order {order_id} not found."}

        current_status = order["status"]
        if current_status == "COMPLETED":
            return {"success": False, "error": f"Order {order_id} is already COMPLETED and cannot be collected again."}

        if current_status not in VALID_TRANSITIONS:
            return {
                "success": False,
                "error": f"Cannot advance order from '{current_status}'. Order must be CONFIRMED first.",
            }

        next_status = VALID_TRANSITIONS[current_status]
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn.execute("""
            UPDATE orders SET status = ?, updated_at = ? WHERE order_id = ?
        """, (next_status, now_str, order_id))

        return {
            "success": True,
            "order_id": order_id,
            "previous_status": current_status,
            "status": next_status,
            "message": f"Order {order_id} advanced from {current_status} to {next_status}.",
        }


def toggle_item_availability(item_id: int, is_globally_available: bool, reason: Optional[str] = None) -> Dict[str, Any]:
    """Staff toggles operational item availability across all slots (Condition 5)."""
    with get_db() as conn:
        item = conn.execute("SELECT name FROM menu_items WHERE item_id = ?", (item_id,)).fetchone()
        if not item:
            return {"success": False, "error": f"Menu item {item_id} not found."}

        clean_reason = None if is_globally_available else (reason or "Temporarily unavailable due to operational restriction")
        conn.execute("""
            UPDATE menu_items
            SET is_globally_available = ?, unavailability_reason = ?
            WHERE item_id = ?
        """, (1 if is_globally_available else 0, clean_reason, item_id))

        state_label = "Available" if is_globally_available else f"Unavailable ({clean_reason})"
        return {
            "success": True,
            "item_id": item_id,
            "name": item["name"],
            "is_globally_available": is_globally_available,
            "message": f"'{item['name']}' marked as {state_label}.",
        }


# =====================================================================
# 3. FASTAPI REST ENDPOINTS LAYER (OPTIONAL HTTP SERVER)
# =====================================================================

if FASTAPI_AVAILABLE:
    app = FastAPI(title="Campus Food Pre-Order API", version="1.0.0")

    class OrderItemPayload(BaseModel):
        item_id: int
        quantity: int

    class SubmitOrderPayload(BaseModel):
        customer_name: str
        slot_id: int
        items: List[OrderItemPayload]

    class ReasonPayload(BaseModel):
        customer_name: Optional[str] = None
        reason: str = "Action requested"

    class AvailabilityPayload(BaseModel):
        is_globally_available: bool
        reason: Optional[str] = None

    @app.on_event("startup")
    def on_startup():
        init_and_seed_db()

    @app.get("/api/slots")
    def api_get_slots():
        return get_pickup_slots()

    @app.get("/api/menu")
    def api_get_menu(slot_id: int = Query(..., description="Pickup Slot ID")):
        return get_menu_by_slot(slot_id)

    @app.post("/api/orders", status_code=201)
    def api_submit_order(payload: SubmitOrderPayload):
        items_dict = [{"item_id": i.item_id, "quantity": i.quantity} for i in payload.items]
        res = submit_preorder(payload.customer_name, payload.slot_id, items_dict)
        if not res["success"]:
            raise HTTPException(status_code=409, detail=res)
        return res

    @app.get("/api/orders")
    def api_list_orders(
        customer_name: Optional[str] = None,
        slot_id: Optional[int] = None,
        status: Optional[str] = None
    ):
        return get_orders(customer_name=customer_name, slot_id=slot_id, status=status)

    @app.post("/api/orders/{order_id}/cancel")
    def api_cancel_order(order_id: str, payload: ReasonPayload):
        res = cancel_order(order_id, payload.customer_name, payload.reason)
        if not res["success"]:
            raise HTTPException(status_code=409, detail=res["error"])
        return res

    @app.post("/api/staff/orders/{order_id}/confirm")
    def api_confirm_order(order_id: str):
        res = confirm_preorder(order_id)
        if not res["success"]:
            raise HTTPException(status_code=409, detail=res["error"])
        return res

    @app.post("/api/staff/orders/{order_id}/reject")
    def api_reject_order(order_id: str, payload: ReasonPayload):
        res = reject_preorder(order_id, payload.reason)
        if not res["success"]:
            raise HTTPException(status_code=409, detail=res["error"])
        return res

    @app.post("/api/staff/orders/{order_id}/advance")
    def api_advance_order(order_id: str):
        res = advance_order_stage(order_id)
        if not res["success"]:
            raise HTTPException(status_code=400, detail=res["error"])
        return res

    @app.patch("/api/staff/menu/{item_id}")
    def api_toggle_item(item_id: int, payload: AvailabilityPayload):
        res = toggle_item_availability(item_id, payload.is_globally_available, payload.reason)
        if not res["success"]:
            raise HTTPException(status_code=404, detail=res["error"])
        return res

    @app.post("/api/admin/reset")
    def api_reset_db():
        init_and_seed_db(force_reset=True)
        return {"message": "Database reset to initial 4 August 2026 seed data."}


# =====================================================================
# 4. SELF-TEST / CLI VERIFICATION
# =====================================================================
if __name__ == "__main__":
    print("Initializing and seeding database...")
    init_and_seed_db(force_reset=True)

    # Verify Slot 3 (13:00-13:30) initial state
    menu_1300 = get_menu_by_slot(slot_id=3)
    print("\n--- Initial Menu for 13:00-13:30 (4 Aug 2026) ---")
    for m in menu_1300:
        print(f"{m['name']:18} | Max: {m['max_qty']:2} | Committed: {m['committed_qty']:2} | Avail: {m['available_qty']:2} | GlobalOK: {m['is_globally_available']}")

    # Test 1: Conflict Scenario (Ordering 15 Veg Sandwiches in 13:00-13:30 when only 12 left)
    print("\n--- Test 1: Over-Ordering Conflict + Smart Alternative Slot Suggestion ---")
    conflict_res = submit_preorder("Student_101", slot_id=3, items=[{"item_id": 1, "quantity": 15}])
    print(conflict_res)

    # Test 2: Valid Order -> Confirm -> Cancel Before Prep -> Verify Inventory Released
    print("\n--- Test 2: Happy Path Submit -> Confirm -> Cancel (Inventory Release) ---")
    ok_res = submit_preorder("Student_101", slot_id=3, items=[{"item_id": 1, "quantity": 4}])
    print("Submitted:", ok_res)
    oid = ok_res["order_id"]
    print("After Submit Veg Sandwich Avail:", get_menu_by_slot(3)[0]["available_qty"])  # Should be 8 (12 - 4)
    print("Confirmed:", confirm_preorder(oid))
    print("Cancelled:", cancel_order(oid, "Student_101", "Class rescheduled"))
    print("After Cancel Veg Sandwich Avail:", get_menu_by_slot(3)[0]["available_qty"])  # Back to 12!