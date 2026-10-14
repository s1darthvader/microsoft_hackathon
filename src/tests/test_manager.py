"""Manager rules: capacity floor (BR-20 / V-13), policy validation, flag scope."""
import pytest

from core.rules import BusinessRuleError
from helpers import D4, MAIN, available, item_id, outlet_id, place, set_policy, slot_id
from services import menu


def set_capacity(item, start, value, outlet=MAIN):
    menu.set_capacity(outlet_id(outlet), slot_id(D4, start), item_id(item), value)


def test_capacity_cannot_go_below_counted():
    with pytest.raises(BusinessRuleError, match="Cannot set capacity to 6: 8 units are already counted"):
        set_capacity("Veg Sandwich", "13:00", 6)
    assert available(MAIN, "13:00", "Veg Sandwich") == 12


def test_capacity_at_counted_is_allowed_and_sells_out():
    set_capacity("Veg Sandwich", "13:00", 8)
    assert available(MAIN, "13:00", "Veg Sandwich") == 0


def test_capacity_increase_adds_stock():
    set_capacity("Veg Sandwich", "13:00", 25)
    assert available(MAIN, "13:00", "Veg Sandwich") == 17
    assert place(MAIN, "13:00", {"Veg Sandwich": 17})["status"] == "Pending Confirmation"


def test_capacity_rejects_non_whole_numbers():
    with pytest.raises(BusinessRuleError):
        set_capacity("Veg Sandwich", "13:00", -1)


def test_policy_threshold_must_be_positive():
    with pytest.raises(BusinessRuleError):
        set_policy(MAIN, True, 0)


def test_policy_threshold_moves_the_bulk_line():
    set_policy(MAIN, True, 3)
    assert place(MAIN, "13:00", {"Masala Dosa": 3})["status"] == "Confirmed"
    assert place(MAIN, "13:00", {"Masala Dosa": 4})["review_reason"] == "Bulk order"


def test_flag_requires_a_known_reason():
    with pytest.raises(BusinessRuleError, match="reason is required"):
        menu.set_unavailable(outlet_id(MAIN), item_id("Masala Dosa"), D4, None, True, "")
    with pytest.raises(BusinessRuleError, match="Choose one of"):
        menu.set_unavailable(outlet_id(MAIN), item_id("Masala Dosa"), D4, None, True, "Bored")


def test_flag_for_one_slot_leaves_others_open():
    menu.set_unavailable(outlet_id(MAIN), item_id("Masala Dosa"), D4, slot_id(D4, "13:00"), True, "Sold out")
    assert available(MAIN, "13:00", "Masala Dosa") == 0
    assert available(MAIN, "12:30", "Masala Dosa") == 15


def test_unflag_restores_availability():
    menu.set_unavailable(outlet_id(MAIN), item_id("Cold Coffee"), D4, None, False, None)
    assert available(MAIN, "13:00", "Cold Coffee") == 18


def test_cannot_flag_another_outlets_item():
    with pytest.raises(BusinessRuleError, match="does not belong"):
        menu.set_unavailable(outlet_id(MAIN), item_id("Samosa"), D4, None, True, "Sold out")
