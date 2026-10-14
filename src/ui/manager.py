"""Outlet manager view: availability flags, confirmation policy, demand, capacity (FR-M1 .. FR-M4)."""
import streamlit as st

from core.rules import UNAVAILABLE_REASONS
from services import availability, clock, menu, notifications, queries
from ui import common


def render(ctx: dict) -> None:
    outlet_id = ctx["outlet_id"]
    outlet = next(o for o in queries.list_outlets() if o["id"] == outlet_id)
    common.inbox(notifications.outlet_key(outlet_id), "Outlet notifications")
    items = queries.list_items(outlet_id)
    dates = queries.list_dates()

    left, right = st.columns(2)
    with left:
        _flag_form(outlet_id, items, dates)
    with right:
        _policy_form(outlet)
    st.divider()
    _demand(outlet_id, dates)


def _slot_choice(key: str, dates: list, allow_all: bool) -> tuple:
    date = st.selectbox("Date", dates, format_func=clock.long_date, key=f"{key}_date")
    slots = queries.list_slots(date)
    options = ([None] if allow_all else []) + slots
    slot = st.selectbox(
        "Pickup slot", options, key=f"{key}_slot",
        format_func=lambda s: "All slots on this date" if s is None else clock.slot_label(s))
    return date, slot


def _flag_form(outlet_id: int, items: list, dates: list) -> None:
    st.subheader("Item availability")
    item = st.selectbox("Item", items, format_func=lambda i: i["name"], key="flag_item")
    date, slot = _slot_choice("flag", dates, allow_all=True)
    mode = st.radio("Action", ["Flag unavailable", "Make available again"], horizontal=True)
    flagged = mode == "Flag unavailable"
    reason = st.selectbox("Reason", UNAVAILABLE_REASONS) if flagged else None
    if st.button("Apply", key="flag_apply"):
        common.run_action(
            menu.set_unavailable, outlet_id, item["item_id"], date,
            slot["id"] if slot else None, flagged, reason,
            success=lambda n: (
                f"{item['name']} flagged unavailable. {n} existing order(s) affected; "
                "staff decide whether to keep or cancel them." if flagged
                else f"{item['name']} is available again."))


def _policy_form(outlet: dict) -> None:
    st.subheader("Confirmation policy")
    auto = st.checkbox("Auto-confirm ordinary pre-orders", value=bool(outlet["auto_confirm"]),
                       key=f"auto_{outlet['id']}")
    threshold = st.number_input(
        "Bulk review threshold (units per order)", min_value=1, step=1,
        value=int(outlet["bulk_review_threshold"]), key=f"threshold_{outlet['id']}")
    st.caption("Orders above the threshold, or any order when auto-confirm is off, wait for staff.")
    if st.button("Save policy"):
        common.run_action(
            menu.set_outlet_policy, outlet["id"], auto, int(threshold), success="Policy saved.")


def _demand(outlet_id: int, dates: list) -> None:
    st.subheader("Slot demand")
    date, slot = _slot_choice("demand", dates, allow_all=False)
    rows = availability.get_availability(outlet_id, slot["id"])
    st.dataframe(
        [{"Item": r["name"], "Capacity": r["capacity"], "Counted": r["counted"],
          "Available": r["available"], "State": r["state"].replace("_", " ")} for r in rows],
        hide_index=True)

    st.markdown("**Change capacity for this slot**")
    c1, c2, c3 = st.columns([3, 2, 1])
    item = c1.selectbox("Item", rows, format_func=lambda r: r["name"], key="cap_item")
    new_capacity = c2.number_input(
        "New capacity", min_value=0, step=1, value=int(item["capacity"]),
        key=f"cap_value_{slot['id']}_{item['item_id']}")
    if c3.button("Save", key="cap_save"):
        common.run_action(
            menu.set_capacity, outlet_id, slot["id"], item["item_id"], int(new_capacity),
            success=f"{item['name']} capacity set to {int(new_capacity)}.")
