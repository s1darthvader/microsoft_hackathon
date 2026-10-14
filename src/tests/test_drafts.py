"""Drafts: cart and typed reasons survive sign-out, per user."""
from core.seed import DEMO_PASSWORD, reset_demo_data
from services import auth, drafts


def _uid(username):
    return auth.authenticate(username, DEMO_PASSWORD)["id"]


def test_round_trip_and_overwrite():
    uid = _uid("student1")
    assert drafts.load(uid, "cart") is None
    drafts.save(uid, "cart", {"slot_id": 3, "quantities": {"1": 2}})
    drafts.save(uid, "cart", {"slot_id": 4, "quantities": {"1": 5}})
    assert drafts.load(uid, "cart") == {"slot_id": 4, "quantities": {"1": 5}}


def test_clear_and_default():
    uid = _uid("canteen.staff")
    drafts.save(uid, "reason_7", "Kitchen closed")
    drafts.clear(uid, "reason_7")
    assert drafts.load(uid, "reason_7", "") == ""


def test_prefix_load_does_not_treat_underscore_as_wildcard():
    uid = _uid("canteen.staff")
    drafts.save(uid, "reason_1", "a")
    drafts.save(uid, "reasonX2", "b")
    assert drafts.load_prefix(uid, "reason_") == {"reason_1": "a"}


def test_drafts_are_per_user():
    drafts.save(_uid("student1"), "cart", {"x": 1})
    assert drafts.load(_uid("student2"), "cart") is None


def test_reset_clears_drafts():
    drafts.save(_uid("student1"), "cart", {"x": 1})
    reset_demo_data()
    assert drafts.load(_uid("student1"), "cart") is None
