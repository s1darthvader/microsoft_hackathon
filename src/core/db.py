"""SQLite access: one connection per operation, explicit transactions (NFR-02)."""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "campus_food.db"

SCHEMA_VERSION = "2"  # bump when SCHEMA changes; init_db reseeds an older database

TABLES = (
    "draft", "app_user", "notification", "order_status_history", "order_line", "orders",
    "slot_item_availability", "pickup_slot", "menu_item", "outlet", "app_setting",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS outlet (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    auto_confirm INTEGER NOT NULL DEFAULT 1,
    bulk_review_threshold INTEGER NOT NULL DEFAULT 10
);
CREATE TABLE IF NOT EXISTS menu_item (
    id INTEGER PRIMARY KEY,
    outlet_id INTEGER NOT NULL REFERENCES outlet(id),
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    default_qty_per_slot INTEGER NOT NULL CHECK (default_qty_per_slot > 0),
    price INTEGER NOT NULL DEFAULT 0 CHECK (price >= 0),
    UNIQUE (outlet_id, name)
);
CREATE TABLE IF NOT EXISTS pickup_slot (
    id INTEGER PRIMARY KEY,
    date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    UNIQUE (date, start_time)
);
CREATE TABLE IF NOT EXISTS slot_item_availability (
    slot_id INTEGER NOT NULL REFERENCES pickup_slot(id),
    item_id INTEGER NOT NULL REFERENCES menu_item(id),
    capacity INTEGER NOT NULL CHECK (capacity >= 0),
    is_unavailable INTEGER NOT NULL DEFAULT 0,
    unavailable_reason TEXT,
    PRIMARY KEY (slot_id, item_id)
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    outlet_id INTEGER NOT NULL REFERENCES outlet(id),
    slot_id INTEGER NOT NULL REFERENCES pickup_slot(id),
    customer_id TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN (
        'Pending Confirmation', 'Confirmed', 'Preparing', 'Ready',
        'Collected', 'Rejected', 'Cancelled')),
    pickup_code TEXT NOT NULL,
    review_reason TEXT,
    closure_reason TEXT,
    payment_ref TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS order_line (
    order_id INTEGER NOT NULL REFERENCES orders(id),
    item_id INTEGER NOT NULL REFERENCES menu_item(id),
    quantity INTEGER NOT NULL CHECK (quantity >= 1),
    PRIMARY KEY (order_id, item_id)
);
CREATE TABLE IF NOT EXISTS order_status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    from_status TEXT,
    to_status TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT,
    timestamp TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_setting (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notification (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipient TEXT NOT NULL,
    order_id INTEGER REFERENCES orders(id),
    message TEXT NOT NULL,
    created_at TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS app_user (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    salt TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN (
        'Customer', 'Outlet Staff', 'Outlet Manager', 'Campus Admin')),
    display_name TEXT NOT NULL,
    campus_id TEXT,
    outlet_id INTEGER REFERENCES outlet(id)
);
CREATE TABLE IF NOT EXISTS draft (
    user_id INTEGER NOT NULL REFERENCES app_user(id),
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id, key)
);
"""


def db_path() -> str:
    """Read per call so tests can point CAMPUS_FOOD_DB at a temp file."""
    return os.environ.get("CAMPUS_FOOD_DB", str(DEFAULT_DB))


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), isolation_level=None, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def read():
    """Read-only connection, closed on exit."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def tx():
    """BEGIN IMMEDIATE ... COMMIT, so check-and-write is atomic (BR-05).

    The write lock is taken before the first read, so two concurrent
    submits cannot both see the same last unit.
    """
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
    finally:
        conn.close()


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def drop_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("".join(f"DROP TABLE IF EXISTS {t};" for t in TABLES))
