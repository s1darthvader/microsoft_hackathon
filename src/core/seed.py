"""Seed data (spec section 9) and the init/reset entry points (FR-X1)."""
from functools import lru_cache

from core.db import SCHEMA_VERSION, connect, create_schema, drop_schema, tx
from core.passwords import demo_salt, hash_password
from core.rules import CONFIRMED, SYSTEM

CLOCK_START = "2026-08-04 10:00:00"
DEMO_PASSWORD = "demo123"  # every seeded account; shown on the login screen
SEED_CREATED_AT = "2026-08-04 09:00:00"

SEED = {
    # (name, auto_confirm, bulk_review_threshold)
    "outlets": [("Main Canteen", 1, 10), ("Snack Kiosk", 1, 10)],
    # (outlet, name, category, capacity per slot, price in rupees)
    "items": [
        ("Main Canteen", "Veg Sandwich", "Snacks", 20, 40),
        ("Main Canteen", "Masala Dosa", "South Indian", 15, 60),
        ("Main Canteen", "Paneer Rice Bowl", "Meals", 12, 90),
        ("Main Canteen", "Cold Coffee", "Beverages", 18, 50),
        ("Main Canteen", "Fruit Bowl", "Healthy Meals", 10, 45),
        ("Snack Kiosk", "Samosa", "Snacks", 25, 15),
        ("Snack Kiosk", "Masala Chai", "Beverages", 30, 12),
    ],
    # (username, role, display name, campus id, outlet)
    "users": [
        ("student1", "Customer", "Asha Rao", "S101", None),
        ("student2", "Customer", "Ravi Kumar", "S102", None),
        ("canteen.staff", "Outlet Staff", "Canteen Staff", None, "Main Canteen"),
        ("kiosk.staff", "Outlet Staff", "Kiosk Staff", None, "Snack Kiosk"),
        ("canteen.mgr", "Outlet Manager", "Canteen Manager", None, "Main Canteen"),
        ("kiosk.mgr", "Outlet Manager", "Kiosk Manager", None, "Snack Kiosk"),
        ("admin", "Campus Admin", "Campus Admin", None, None),
    ],
    "dates": ["2026-08-04", "2026-08-05"],
    "slot_times": [("12:00", "12:30"), ("12:30", "13:00"), ("13:00", "13:30"), ("13:30", "14:00")],
    # (item, date, reason): flagged unavailable in every slot on that date
    "flags": [("Cold Coffee", "2026-08-04", "Operational restriction")],
    # Pre-committed quantities as real Confirmed orders (A5)
    # (customer name, outlet, date, slot start, {item: quantity})
    "orders": [
        ("Seed – Event booking", "Main Canteen", "2026-08-04", "13:00", {"Veg Sandwich": 8}),
        ("Seed – Placement cell", "Main Canteen", "2026-08-04", "12:30", {"Paneer Rice Bowl": 5}),
        ("Seed – Workshop batch", "Main Canteen", "2026-08-04", "13:00", {"Fruit Bowl": 4}),
    ],
}


@lru_cache(maxsize=None)
def _demo_hash(salt: str) -> str:
    """PBKDF2 is slow by design; tests reseed constantly, so hash each demo account once."""
    return hash_password(DEMO_PASSWORD, salt)


def seed(conn) -> None:
    """Insert the seed data. Call inside a transaction on an empty schema."""
    outlets = {}
    for name, auto, threshold in SEED["outlets"]:
        cur = conn.execute(
            "INSERT INTO outlet (name, auto_confirm, bulk_review_threshold) VALUES (?, ?, ?)",
            (name, auto, threshold))
        outlets[name] = cur.lastrowid

    items = {}
    for outlet, name, category, capacity, price in SEED["items"]:
        cur = conn.execute(
            "INSERT INTO menu_item (outlet_id, name, category, default_qty_per_slot, price) "
            "VALUES (?, ?, ?, ?, ?)",
            (outlets[outlet], name, category, capacity, price))
        items[name] = cur.lastrowid

    slots = {}
    for date in SEED["dates"]:
        for start, end in SEED["slot_times"]:
            cur = conn.execute(
                "INSERT INTO pickup_slot (date, start_time, end_time) VALUES (?, ?, ?)",
                (date, start, end))
            slots[(date, start)] = cur.lastrowid

    conn.execute(
        "INSERT INTO slot_item_availability (slot_id, item_id, capacity) "
        "SELECT s.id, m.id, m.default_qty_per_slot FROM pickup_slot s CROSS JOIN menu_item m")

    for item, date, reason in SEED["flags"]:
        conn.execute(
            "UPDATE slot_item_availability SET is_unavailable = 1, unavailable_reason = ? "
            "WHERE item_id = ? AND slot_id IN (SELECT id FROM pickup_slot WHERE date = ?)",
            (reason, items[item], date))

    for customer, outlet, date, start, lines in SEED["orders"]:
        cur = conn.execute(
            "INSERT INTO orders (outlet_id, slot_id, customer_id, customer_name, status, "
            "pickup_code, created_at) VALUES (?, ?, 'SEED', ?, ?, '0000', ?)",
            (outlets[outlet], slots[(date, start)], customer, CONFIRMED, SEED_CREATED_AT))
        order_id = cur.lastrowid
        for item, quantity in lines.items():
            conn.execute(
                "INSERT INTO order_line (order_id, item_id, quantity) VALUES (?, ?, ?)",
                (order_id, items[item], quantity))
        conn.execute(
            "INSERT INTO order_status_history (order_id, from_status, to_status, actor, reason, timestamp) "
            "VALUES (?, NULL, ?, ?, 'Seed commitment', ?)",
            (order_id, CONFIRMED, SYSTEM, SEED_CREATED_AT))

    for username, role, display_name, campus_id, outlet in SEED["users"]:
        salt = demo_salt(username)
        conn.execute(
            "INSERT INTO app_user (username, password_hash, salt, role, display_name, campus_id, "
            "outlet_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (username, _demo_hash(salt), salt, role, display_name, campus_id,
             outlets.get(outlet)))

    conn.execute("INSERT INTO app_setting (key, value) VALUES ('app_clock', ?)", (CLOCK_START,))
    conn.execute("INSERT INTO app_setting (key, value) VALUES ('schema_version', ?)", (SCHEMA_VERSION,))


def _outdated(conn) -> bool:
    """True for a database built by an older SCHEMA (CREATE IF NOT EXISTS cannot add columns)."""
    try:
        row = conn.execute("SELECT value FROM app_setting WHERE key = 'schema_version'").fetchone()
    except Exception:
        return False  # no tables yet
    has_data = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'outlet'").fetchone()
    return bool(has_data) and (row is None or row["value"] != SCHEMA_VERSION)


def init_db() -> None:
    """Create tables if missing and seed an empty database; reseed an outdated one."""
    conn = connect()
    try:
        if _outdated(conn):
            drop_schema(conn)
        create_schema(conn)
    finally:
        conn.close()
    with tx() as conn:
        if conn.execute("SELECT COUNT(*) FROM outlet").fetchone()[0] == 0:
            seed(conn)


def reset_demo_data() -> None:
    """Drop everything and reload the seed data."""
    conn = connect()
    try:
        drop_schema(conn)
    finally:
        conn.close()
    init_db()
