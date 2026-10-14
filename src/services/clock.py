"""App clock and slot time helpers (FR-X3, BR-21, A3).

Every timestamp and every slot cut-off uses this clock, never the real one.
"""
from datetime import datetime

from core.db import read, tx

FMT = "%Y-%m-%d %H:%M:%S"


def get_now(conn) -> datetime:
    row = conn.execute("SELECT value FROM app_setting WHERE key = 'app_clock'").fetchone()
    return datetime.strptime(row["value"], FMT)


def now_str(conn) -> str:
    return get_now(conn).strftime(FMT)


def current_now() -> datetime:
    with read() as conn:
        return get_now(conn)


def set_now(value: datetime) -> None:
    with tx() as conn:
        conn.execute(
            "INSERT INTO app_setting (key, value) VALUES ('app_clock', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (value.strftime(FMT),))


def slot_start(slot) -> datetime:
    return datetime.strptime(f"{slot['date']} {slot['start_time']}", "%Y-%m-%d %H:%M")


def slot_end(slot) -> datetime:
    return datetime.strptime(f"{slot['date']} {slot['end_time']}", "%Y-%m-%d %H:%M")


def slot_label(slot) -> str:
    return f"{slot['start_time']}–{slot['end_time']}"


def long_date(date: str) -> str:
    d = datetime.strptime(date, "%Y-%m-%d")
    return f"{d.day} {d:%b %Y}"
