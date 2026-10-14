"""End-to-end scenarios: AT-01 and AT-13."""
from datetime import datetime

import pytest

from core.rules import STAFF, BusinessRuleError
from helpers import MAIN, act, available, history, place, status
from services import clock


def test_at01_full_lifecycle():
    assert available(MAIN, "13:00", "Veg Sandwich") == 12
    assert available(MAIN, "13:00", "Masala Dosa") == 15
    order = place(MAIN, "13:00", {"Veg Sandwich": 2, "Masala Dosa": 1})
    oid = order["order_id"]
    assert order["status"] == "Confirmed" and order["review_reason"] is None

    act(oid, "start_preparation", STAFF)
    act(oid, "mark_ready", STAFF)
    act(oid, "mark_collected", STAFF, pickup_code=order["pickup_code"])

    assert status(oid) == "Collected"
    assert [to for _, to, _ in history(oid)] == [
        "Pending Confirmation", "Confirmed", "Preparing", "Ready", "Collected"]
    assert available(MAIN, "13:00", "Veg Sandwich") == 10
    assert available(MAIN, "13:00", "Masala Dosa") == 14


def test_at13_started_slot_is_refused():
    clock.set_now(datetime(2026, 8, 4, 12, 45))
    with pytest.raises(BusinessRuleError, match="already started"):
        place(MAIN, "12:30", {"Masala Dosa": 1})
    assert place(MAIN, "13:00", {"Masala Dosa": 1})["status"] == "Confirmed"
