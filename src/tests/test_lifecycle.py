"""State machine, confirmation and cancellation: AT-07 .. AT-11, AT-14, AT-15, AT-17."""
import pytest

from core.rules import CUSTOMER, STAFF, BusinessRuleError
from helpers import MAIN, act, available, flag, history, place, set_policy, status, stock
from services import queries


def test_at07_reject_releases_stock_and_is_terminal():
    set_policy(MAIN, False)
    order = place(MAIN, "13:00", {"Fruit Bowl": 6})
    assert order["status"] == "Pending Confirmation"
    assert order["review_reason"] == "Manual confirmation"
    with pytest.raises(BusinessRuleError, match="reason is required"):
        act(order["order_id"], "reject", STAFF)
    act(order["order_id"], "reject", STAFF, reason="Kitchen closed early")
    assert status(order["order_id"]) == "Rejected"
    assert available(MAIN, "13:00", "Fruit Bowl") == 6
    with pytest.raises(BusinessRuleError):
        act(order["order_id"], "confirm", STAFF)


def test_at08_cancel_needs_the_right_pickup_code():
    order = place(MAIN, "13:00", {"Masala Dosa": 3})
    assert order["status"] == "Confirmed"
    with pytest.raises(BusinessRuleError, match="pickup code does not match"):
        act(order["order_id"], "cancel", CUSTOMER, pickup_code="x")
    act(order["order_id"], "cancel", CUSTOMER, pickup_code=order["pickup_code"])
    assert status(order["order_id"]) == "Cancelled"
    assert available(MAIN, "13:00", "Masala Dosa") == 15


def test_at09_no_customer_cancel_once_preparing():
    order = place(MAIN, "13:00", {"Masala Dosa": 1})
    act(order["order_id"], "start_preparation", STAFF)
    with pytest.raises(BusinessRuleError, match="Preparation has already started"):
        act(order["order_id"], "cancel", CUSTOMER, pickup_code=order["pickup_code"])


def test_at10_cannot_collect_twice():
    order = place(MAIN, "13:00", {"Masala Dosa": 1})
    oid, code = order["order_id"], order["pickup_code"]
    act(oid, "start_preparation", STAFF)
    act(oid, "mark_ready", STAFF)
    act(oid, "mark_collected", STAFF, pickup_code=code)
    with pytest.raises(BusinessRuleError, match="cannot be collected again"):
        act(oid, "mark_collected", STAFF, pickup_code=code)
    assert status(oid) == "Collected"


def test_at11_flagged_item_blocks_confirm_but_allows_reject():
    set_policy(MAIN, False)
    order = place(MAIN, "13:00", {"Masala Dosa": 2})
    flag("Masala Dosa", "Ingredient shortage")
    with pytest.raises(BusinessRuleError, match="Cannot confirm: Masala Dosa is now unavailable"):
        act(order["order_id"], "confirm", STAFF)
    act(order["order_id"], "reject", STAFF, reason="Ingredient shortage")
    assert stock(MAIN, "13:00", "Masala Dosa")["counted"] == 0


def test_at14_bulk_order_goes_to_staff_review():
    order = place(MAIN, "13:00", {"Masala Dosa": 12})
    assert order["status"] == "Pending Confirmation"
    assert order["review_reason"] == "Bulk order"
    act(order["order_id"], "confirm", STAFF)
    assert status(order["order_id"]) == "Confirmed"
    assert history(order["order_id"])[-1] == ("Pending Confirmation", "Confirmed", "Staff")


def test_at15_outlet_cancel_after_flag():
    order = place(MAIN, "13:00", {"Masala Dosa": 2})
    oid = order["order_id"]
    assert flag("Masala Dosa", "Ingredient shortage") == 1
    queued = queries.get_order(oid, viewer=STAFF)
    assert queued["affected"] is True
    assert "outlet_cancel" in queued["allowed_actions"]
    with pytest.raises(BusinessRuleError, match="reason is required"):
        act(oid, "outlet_cancel", STAFF)
    act(oid, "outlet_cancel", STAFF, reason="Masala Dosa unavailable")
    final = queries.get_order(oid)
    assert final["status"] == "Cancelled"
    assert final["closure_reason"] == "Masala Dosa unavailable"
    assert stock(MAIN, "13:00", "Masala Dosa")["counted"] == 0


def test_at17_confirm_does_not_recheck_quantity():
    set_policy(MAIN, False)
    order = place(MAIN, "13:00", {"Fruit Bowl": 6})
    assert available(MAIN, "13:00", "Fruit Bowl") == 0
    act(order["order_id"], "confirm", STAFF)
    assert status(order["order_id"]) == "Confirmed"


def test_auto_confirm_is_visible_in_the_timeline():
    order = place(MAIN, "13:00", {"Masala Dosa": 1})
    assert history(order["order_id"]) == [
        (None, "Pending Confirmation", "Customer"),
        ("Pending Confirmation", "Confirmed", "System"),
    ]


def test_cannot_skip_a_step():
    order = place(MAIN, "13:00", {"Masala Dosa": 1})
    with pytest.raises(BusinessRuleError, match="is Confirmed"):
        act(order["order_id"], "mark_ready", STAFF)


def test_customer_cannot_cancel_a_rejected_order():
    set_policy(MAIN, False)
    order = place(MAIN, "13:00", {"Masala Dosa": 1})
    act(order["order_id"], "reject", STAFF, reason="No")
    with pytest.raises(BusinessRuleError, match="is Rejected"):
        act(order["order_id"], "cancel", CUSTOMER, pickup_code=order["pickup_code"])


def test_customer_cannot_use_staff_actions():
    order = place(MAIN, "13:00", {"Masala Dosa": 1})
    with pytest.raises(BusinessRuleError):
        act(order["order_id"], "start_preparation", CUSTOMER)
