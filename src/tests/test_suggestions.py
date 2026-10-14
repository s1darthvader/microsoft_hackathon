"""Next available slot suggestions (section 12 alternative bonus)."""
from datetime import datetime

from helpers import D4, D5, MAIN, item_id, outlet_id, slot_id
from services import clock, ordering, suggestions


def suggest(start, lines, outlet=MAIN, date=D4, limit=3):
    cart = [{"item_id": item_id(n), "quantity": q} for n, q in lines.items()]
    return suggestions.next_available_slots(outlet_id(outlet), slot_id(date, start), cart, limit)


def test_oversized_order_gets_later_slots_where_it_fits():
    found = suggest("13:00", {"Fruit Bowl": 7})
    assert [(s["date"], s["label"]) for s in found] == [
        (D4, "13:30–14:00"), (D5, "12:00–12:30"), (D5, "12:30–13:00")]


def test_only_later_slots_are_suggested():
    found = suggest("13:00", {"Fruit Bowl": 7})
    assert all((s["date"], s["label"]) > (D4, "13:00–13:30") for s in found)


def test_no_suggestion_when_the_slot_would_accept_the_order():
    assert suggest("13:00", {"Masala Dosa": 2}) == []


def test_flagged_item_skips_to_the_next_date():
    found = suggest("13:00", {"Cold Coffee": 1})
    assert found[0]["date"] == D5 and found[0]["label"] == "12:00–12:30"


def test_started_slot_suggests_later_slots():
    clock.set_now(datetime(2026, 8, 4, 13, 15))
    found = suggest("13:00", {"Masala Dosa": 1})
    assert found[0]["label"] == "13:30–14:00"


def test_mixed_outlet_cart_gets_no_suggestions():
    assert suggest("13:00", {"Veg Sandwich": 1, "Samosa": 1}) == []


def test_suggested_slot_can_be_booked_through_full_validation():
    pick = suggest("13:00", {"Fruit Bowl": 7})[0]
    cart = [{"item_id": item_id("Fruit Bowl"), "quantity": 7}]
    result = ordering.submit_order(outlet_id(MAIN), pick["slot_id"], "S101", "Asha", cart)
    assert result["status"] == "Confirmed"  # 7 is under the bulk threshold
