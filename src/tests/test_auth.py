"""Sign-in: seeded accounts per stakeholder, password check, role and outlet from the account."""
from core.seed import DEMO_PASSWORD
from helpers import KIOSK, MAIN, outlet_id
from services import auth


def test_each_stakeholder_signs_in_with_their_role():
    roles = {u: auth.authenticate(u, DEMO_PASSWORD)["role"] for u in
             ("student1", "canteen.staff", "canteen.mgr", "admin")}
    assert roles == {"student1": "Customer", "canteen.staff": "Outlet Staff",
                     "canteen.mgr": "Outlet Manager", "admin": "Campus Admin"}


def test_wrong_password_or_unknown_user_is_refused():
    assert auth.authenticate("student1", "wrong") is None
    assert auth.authenticate("nobody", DEMO_PASSWORD) is None
    assert auth.authenticate("", "") is None


def test_username_is_case_insensitive_and_secrets_are_not_returned():
    user = auth.authenticate("  Student1 ", DEMO_PASSWORD)
    assert user["campus_id"] == "S101"
    assert "password_hash" not in user and "salt" not in user


def test_outlet_accounts_are_bound_to_their_outlet():
    assert auth.authenticate("canteen.staff", DEMO_PASSWORD)["outlet_id"] == outlet_id(MAIN)
    assert auth.authenticate("kiosk.mgr", DEMO_PASSWORD)["outlet_id"] == outlet_id(KIOSK)
    assert auth.authenticate("admin", DEMO_PASSWORD)["outlet_id"] is None


def test_get_user_reloads_by_id():
    user = auth.authenticate("student2", DEMO_PASSWORD)
    assert auth.get_user(user["id"])["display_name"] == "Ravi Kumar"
    assert auth.get_user(9999) is None
