"""Customer view: browse availability, place a pre-order, track and cancel (FR-C1 .. FR-C5)."""
import streamlit as st

from core.rules import (
    CANCELLED, COLLECTED, CUSTOMER, PREPARING, READY, REJECTED,
)
from services import availability, clock, lifecycle, notifications, ordering, queries, suggestions
from ui import common

CANCEL_BLOCKED = {
    PREPARING: "Preparation has already started, so this order can no longer be cancelled.",
    READY: "Preparation has already started, so this order can no longer be cancelled.",
    COLLECTED: "This order has already been collected.",
    REJECTED: "This pre-order was rejected and is closed. Place a new pre-order instead.",
    CANCELLED: "This order is already cancelled.",
}


def _availability_text(row: dict) -> str:
    if row["state"] == "unavailable":
        return f"Unavailable — {row['reason']}"
    if row["state"] == "sold_out":
        return "Sold out"
    return f"{row['available']} available"


def render(ctx: dict) -> None:
    _place_order()
    st.divider()
    _my_orders()


def _place_order() -> None:
    st.subheader("Place a pre-order")
    outlets = queries.list_outlets()
    c1, c2, c3 = st.columns(3)
    outlet = c1.selectbox("Outlet", outlets, format_func=lambda o: o["name"])
    date = c2.selectbox("Date", queries.list_dates(), format_func=clock.long_date)
    slot = c3.selectbox("Pickup slot", queries.list_slots(date), format_func=clock.slot_label)

    menu = availability.get_availability(outlet["id"], slot["id"])
    with st.form("preorder", clear_on_submit=False):
        quantities = {}
        for row in menu:
            name_col, status_col, qty_col = st.columns([3, 3, 2])
            name_col.markdown(f"**{row['name']}**  \n{row['category']}")
            status_col.write(_availability_text(row))
            quantities[row["item_id"]] = qty_col.number_input(
                row["name"], min_value=0, step=1, value=0,
                key=f"qty_{st.session_state.get('form_gen', 0)}_{slot['id']}_{row['item_id']}", label_visibility="collapsed")
        id_col, name_col = st.columns(2)
        customer_id = id_col.text_input("Campus ID", key="order_customer_id")
        customer_name = name_col.text_input("Name", key="order_customer_name")
        submitted = st.form_submit_button("Submit pre-order", type="primary")

    if submitted:
        st.session_state.pop("alternatives", None)
        lines = [{"item_id": i, "quantity": q} for i, q in quantities.items() if q > 0]
        st.session_state["my_orders_id"] = customer_id.strip()
        common.run_action(
            ordering.submit_order, outlet["id"], slot["id"], customer_id, customer_name, lines,
            success=_submitted_message, on_success=_reset_form)
        # Reached only when the submit was refused (success reruns the script).
        slots = suggestions.next_available_slots(outlet["id"], slot["id"], lines)
        if slots:
            st.session_state["alternatives"] = {
                "outlet_id": outlet["id"], "customer_id": customer_id,
                "customer_name": customer_name, "lines": lines, "slots": slots}
    _show_alternatives()


def _show_alternatives() -> None:
    """Offer later slots where the whole order fits; booking re-runs full validation."""
    alt = st.session_state.get("alternatives")
    if not alt:
        return
    st.info("Your whole order fits in these later slots. Pick one to place it there.")
    for slot in alt["slots"]:
        label = f"Book {clock.long_date(slot['date'])} · {slot['label']} instead"
        if st.button(label, key=f"alt_{slot['slot_id']}"):
            st.session_state.pop("alternatives", None)
            common.run_action(
                ordering.submit_order, alt["outlet_id"], slot["slot_id"], alt["customer_id"],
                alt["customer_name"], alt["lines"], success=_submitted_message,
                on_success=_reset_form)


def _reset_form(result: dict) -> None:
    """New quantity widget keys, so a placed order is not resubmitted by a stray click."""
    st.session_state["form_gen"] = st.session_state.get("form_gen", 0) + 1


def _submitted_message(result: dict) -> str:
    text = (
        f"Order #{result['order_id']} placed. Pickup code: {result['pickup_code']} "
        "(keep it: you need it to cancel or collect). "
        f"Status: {result['status']}."
    )
    if result["review_reason"]:
        text += f" Held for staff review ({result['review_reason']})."
    return text


def _my_orders() -> None:
    st.subheader("My orders")
    customer_id = st.text_input("Campus ID", key="my_orders_id")
    if not customer_id.strip():
        st.caption("Enter your campus ID to see your orders.")
        return
    common.inbox(notifications.customer_key(customer_id), "Notifications")
    orders = queries.list_orders(customer_id=customer_id, viewer=CUSTOMER)
    if not orders:
        st.info("No orders found for this campus ID.")
        return
    for o in orders:
        title = f"#{o['id']} · {o['outlet_name']} · {clock.long_date(o['date'])} {o['slot_label']}"
        with st.expander(f"{title} · {o['status']}", expanded=o["status"] not in CANCEL_BLOCKED):
            st.markdown(f"{common.badge(o['status'])} — {common.order_lines(o)}")
            if o["status"] == "Pending Confirmation" and o["review_reason"]:
                st.caption(f"Waiting for staff review: {o['review_reason']}.")
            if o["closure_reason"] and o["status"] in (REJECTED, CANCELLED):
                st.warning(f"Reason: {o['closure_reason']}")
            common.timeline(o["history"])
            _cancel_control(o)


def _cancel_control(o: dict) -> None:
    key = f"cancel_{o['id']}"
    if "cancel" in o["allowed_actions"]:
        code = st.text_input("Pickup code to cancel", key=f"{key}_code", max_chars=4)
        if st.button("Cancel order", key=key):
            common.run_action(
                lifecycle.transition, o["id"], "cancel", CUSTOMER, pickup_code=code,
                success=f"Order #{o['id']} cancelled.")
    else:
        st.button("Cancel order", key=key, disabled=True)
        st.caption(CANCEL_BLOCKED.get(o["status"], "This order cannot be cancelled."))
