"""In-app notifications (section 12): written in the same transaction as the change."""
from core.rules import CUSTOMER, STAFF
from helpers import MAIN, act, flag, outlet_id, place, set_policy
from services import notifications


def customer_messages(customer="S101"):
    return [n["message"] for n in notifications.inbox(notifications.customer_key(customer))]


def outlet_messages():
    return [n["message"] for n in notifications.inbox(notifications.outlet_key(outlet_id(MAIN)))]


def test_ready_notifies_customer_with_slot():
    order = place(MAIN, "13:00", {"Masala Dosa": 1})
    act(order["order_id"], "start_preparation", STAFF)
    act(order["order_id"], "mark_ready", STAFF)
    assert f"Order #{order['order_id']} is Ready for pickup at 13:00–13:30." in customer_messages()


def test_reject_notifies_customer_with_reason():
    set_policy(MAIN, False)
    order = place(MAIN, "13:00", {"Masala Dosa": 1})
    act(order["order_id"], "reject", STAFF, reason="Ingredient shortage")
    assert f"Pre-order #{order['order_id']} was rejected: Ingredient shortage." in customer_messages()


def test_outlet_cancel_notifies_customer_with_outlet_and_reason():
    order = place(MAIN, "13:00", {"Masala Dosa": 1})
    act(order["order_id"], "outlet_cancel", STAFF, reason="Masala Dosa unavailable")
    expected = f"Order #{order['order_id']} was cancelled by Main Canteen: Masala Dosa unavailable."
    assert expected in customer_messages()


def test_customer_cancel_notifies_outlet_not_customer():
    order = place(MAIN, "13:00", {"Masala Dosa": 1})
    before = len(customer_messages())
    act(order["order_id"], "cancel", CUSTOMER, pickup_code=order["pickup_code"])
    assert len(customer_messages()) == before
    assert f"Order #{order['order_id']} was cancelled by the customer." in outlet_messages()


def test_bulk_order_alerts_the_outlet():
    order = place(MAIN, "13:00", {"Masala Dosa": 12})
    assert f"New pre-order #{order['order_id']} needs review (bulk order)." in outlet_messages()


def test_flag_alerts_the_outlet_with_affected_count():
    place(MAIN, "13:00", {"Masala Dosa": 1}, customer="S1")
    place(MAIN, "13:00", {"Masala Dosa": 2}, customer="S2")
    flag("Masala Dosa", "Ingredient shortage")
    assert "Masala Dosa flagged unavailable. 2 order(s) affected." in outlet_messages()


def test_mark_all_read():
    place(MAIN, "13:00", {"Masala Dosa": 1})
    key = notifications.customer_key("S101")
    assert notifications.unread_count(key) >= 1
    notifications.mark_all_read(key)
    assert notifications.unread_count(key) == 0


def test_failed_action_leaves_no_notification():
    set_policy(MAIN, False)
    order = place(MAIN, "13:00", {"Masala Dosa": 1})
    flag("Masala Dosa", "Ingredient shortage")
    before = len(customer_messages())
    try:
        act(order["order_id"], "confirm", STAFF)
    except Exception:
        pass
    assert len(customer_messages()) == before
