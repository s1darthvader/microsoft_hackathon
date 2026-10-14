"""Submit and availability rules: AT-02 .. AT-06, AT-16, AT-18 and the section 15 edge cases."""
import pytest

from core.rules import BusinessRuleError
from helpers import D4, D5, KIOSK, MAIN, available, item_id, outlet_id, place, slot_id, stock
from services import ordering, queries


def test_seed_matches_section_9():
    assert available(MAIN, "13:00", "Veg Sandwich") == 12
    assert available(MAIN, "12:00", "Veg Sandwich") == 20
    assert available(MAIN, "12:30", "Paneer Rice Bowl") == 7
    assert available(MAIN, "13:00", "Fruit Bowl") == 6
    assert available(MAIN, "13:00", "Masala Dosa") == 15
    assert stock(MAIN, "13:00", "Cold Coffee")["state"] == "unavailable"
    assert available(MAIN, "13:00", "Cold Coffee", date=D5) == 18


def test_at02_over_ask_refused_and_stock_unchanged():
    with pytest.raises(BusinessRuleError, match="only 12 are available"):
        place(MAIN, "13:00", {"Veg Sandwich": 13})
    assert available(MAIN, "13:00", "Veg Sandwich") == 12


def test_at03_one_failing_line_blocks_the_whole_order():
    with pytest.raises(BusinessRuleError) as err:
        place(MAIN, "13:00", {"Masala Dosa": 2, "Fruit Bowl": 7})
    assert "Fruit Bowl" in str(err.value)
    assert "Nothing has been reserved" in str(err.value)
    assert available(MAIN, "13:00", "Masala Dosa") == 15


def test_all_failing_lines_are_listed_together():
    with pytest.raises(BusinessRuleError) as err:
        place(MAIN, "13:00", {"Veg Sandwich": 13, "Fruit Bowl": 7})
    assert len(err.value.lines) == 2


def test_at04_flag_is_per_date():
    with pytest.raises(BusinessRuleError, match="Operational restriction"):
        place(MAIN, "13:00", {"Cold Coffee": 1})
    assert place(MAIN, "13:00", {"Cold Coffee": 1}, date=D5)["status"] == "Confirmed"


def test_at05_slots_are_isolated():
    with pytest.raises(BusinessRuleError):
        place(MAIN, "12:30", {"Paneer Rice Bowl": 8})
    assert place(MAIN, "13:00", {"Paneer Rice Bowl": 8})["status"] == "Confirmed"


def test_at06_last_units_then_sold_out():
    place(MAIN, "13:00", {"Fruit Bowl": 6}, customer="S1", name="A")
    row = stock(MAIN, "13:00", "Fruit Bowl")
    assert row["available"] == 0 and row["state"] == "sold_out"
    with pytest.raises(BusinessRuleError):
        place(MAIN, "13:00", {"Fruit Bowl": 1}, customer="S2", name="B")


def test_at16_mixed_outlet_cart_refused():
    with pytest.raises(BusinessRuleError, match="sold by Snack Kiosk"):
        place(MAIN, "13:00", {"Veg Sandwich": 1, "Samosa": 1})
    assert available(MAIN, "13:00", "Veg Sandwich") == 12
    assert available(KIOSK, "13:00", "Samosa") == 25


def test_at18_outlets_are_isolated():
    place(KIOSK, "13:00", {"Samosa": 5})
    assert available(KIOSK, "13:00", "Samosa") == 20
    assert available(MAIN, "13:00", "Veg Sandwich") == 12
    assert available(MAIN, "13:00", "Fruit Bowl") == 6


@pytest.mark.parametrize("qty", [0, -1, 2.5])
def test_bad_quantities_refused(qty):
    with pytest.raises(BusinessRuleError, match="whole-number quantity"):
        place(MAIN, "13:00", {"Masala Dosa": qty})


def test_duplicate_lines_are_merged():
    cart = [{"item_id": item_id("Masala Dosa"), "quantity": 2},
            {"item_id": item_id("Masala Dosa"), "quantity": 3}]
    result = ordering.submit_order(outlet_id(MAIN), slot_id(D4, "13:00"), "S1", "A", cart)
    order = queries.get_order(result["order_id"])
    assert [(line["name"], line["quantity"]) for line in order["lines"]] == [("Masala Dosa", 5)]


def test_blank_identity_refused():
    with pytest.raises(BusinessRuleError, match="campus ID and name"):
        place(MAIN, "13:00", {"Masala Dosa": 1}, customer=" ", name="Asha")


def test_pickup_code_is_four_digits():
    code = place(MAIN, "13:00", {"Masala Dosa": 1})["pickup_code"]
    assert len(code) == 4 and code.isdigit()
