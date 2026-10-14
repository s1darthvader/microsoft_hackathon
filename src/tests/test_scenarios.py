"""End-to-end scenarios: AT-01 and AT-13."""
from datetime import datetime

import pytest

from core.rules import STAFF, BusinessRuleError
from helpers import D4, MAIN, act, available, history, item_id, outlet_id, place, slot_id, status
from services import clock, ordering, queries


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


def test_demo_payment_reference_and_total_are_recorded():
    result = ordering.submit_order(
        outlet_id(MAIN), slot_id(D4, "12:00"), "S101", "Asha",
        [{"item_id": item_id("Masala Dosa"), "quantity": 2},
         {"item_id": item_id("Veg Sandwich"), "quantity": 1}],
        payment_ref="DEMO-abc123")
    assert result["total"] == 2 * 60 + 40
    order = queries.get_order(result["order_id"])
    assert order["payment_ref"] == "DEMO-abc123" and order["total"] == 160
