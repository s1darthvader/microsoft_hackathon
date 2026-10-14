"""Customer view: browse availability, build a saved cart, demo checkout, track and cancel (FR-C1 .. FR-C5)."""
import re
import secrets

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
PAY_METHODS = ("Card", "UPI", "Pay at counter")


def _availability_text(row: dict) -> str:
    if row["state"] == "unavailable":
        return f"Unavailable — {row['reason']}"
    if row["state"] == "sold_out":
        return "Sold out"
    return f"{row['available']} available"


def _money(amount: int) -> str:
    return f"₹{amount:,}"


def render(ctx: dict) -> None:
    user = ctx["user"]
    if st.session_state.get("checkout"):
        _checkout(user)
    else:
        _place_order(user)
    st.divider()
    _my_orders(user)


def _place_order(user: dict) -> None:
    """Outlet, slot and quantities are drafts: they survive sign-out, refresh and slot changes."""
    st.subheader("Place a pre-order")
    uid = user["id"]
    outlets = {o["id"]: o for o in queries.list_outlets()}
    dates = queries.list_dates()
    c1, c2, c3 = st.columns(3)
    outlet_id = c1.selectbox(
        "Outlet", list(outlets), format_func=lambda i: outlets[i]["name"],
        **common.persist(uid, "cart_outlet", next(iter(outlets)), list(outlets)))
    date = c2.selectbox(
        "Date", dates, format_func=clock.long_date,
        **common.persist(uid, "cart_date", dates[0], dates))
    slots = {s["id"]: s for s in queries.list_slots(date)}
    slot_id = c3.selectbox(
        "Pickup slot", list(slots), format_func=lambda i: clock.slot_label(slots[i]),
        **common.persist(uid, "cart_slot", next(iter(slots)), list(slots)))

    menu = availability.get_availability(outlet_id, slot_id)
    quantities = {}
    for row in menu:
        name_col, status_col, qty_col = st.columns([3, 3, 2])
        name_col.markdown(f"**{row['name']}** · {_money(row['price'])}  \n{row['category']}")
        status_col.write(_availability_text(row))
        quantities[row["item_id"]] = qty_col.number_input(
            row["name"], min_value=0, step=1, label_visibility="collapsed",
            **common.persist(uid, f"qty_{outlet_id}_{row['item_id']}", 0))

    picked = [row for row in menu if quantities[row["item_id"]] > 0]
    total = sum(row["price"] * quantities[row["item_id"]] for row in picked)
    st.markdown(f"**Cart total: {_money(total)}**" if picked else "_Your cart is empty._")
    st.caption("Your selection is saved automatically, even if you sign out.")
    if st.button("Review & pay", type="primary", disabled=not picked):
        st.session_state.pop("alternatives", None)
        st.session_state["checkout"] = {
            "outlet_id": outlet_id, "outlet_name": outlets[outlet_id]["name"],
            "slot": slots[slot_id],
            "lines": [{"item_id": r["item_id"], "name": r["name"], "price": r["price"],
                       "quantity": quantities[r["item_id"]]} for r in picked],
        }
        st.rerun()


def _checkout(user: dict) -> None:
    """Demo payment: nothing is charged and no payment details are stored (A10)."""
    co = st.session_state["checkout"]
    slot = co["slot"]
    total = sum(line["price"] * line["quantity"] for line in co["lines"])
    st.subheader("Checkout")
    st.caption(f"{co['outlet_name']} · {clock.long_date(slot['date'])} · {clock.slot_label(slot)}")
    st.dataframe(
        [{"Item": line["name"], "Qty": line["quantity"], "Price": _money(line["price"]),
          "Amount": _money(line["price"] * line["quantity"])} for line in co["lines"]],
        hide_index=True)
    st.markdown(f"### Total {_money(total)}")
    st.info("Demo payment screen: no money is taken and nothing you type here is stored.")

    method = st.radio("Payment method", PAY_METHODS, horizontal=True, key="pay_method")
    # A form, so every payment field reaches the server together with the Pay click.
    with st.form("payment", border=False):
        fields = {}
        if method == "Card":
            c1, c2, c3 = st.columns([3, 1, 1])
            fields["card"] = c1.text_input("Card number", placeholder="4111 1111 1111 1111")
            fields["expiry"] = c2.text_input("Expiry", placeholder="MM/YY", max_chars=5)
            fields["cvv"] = c3.text_input("CVV", type="password", max_chars=4)
        elif method == "UPI":
            fields["upi"] = st.text_input("UPI ID", placeholder="name@bank")
        else:
            st.caption("Pay when you collect. Your order is reserved now.")
        label = "Place order" if method == "Pay at counter" else f"Pay {_money(total)}"
        pay = st.form_submit_button(label, type="primary")
    if st.button("Back to cart"):
        st.session_state.pop("checkout", None)
        st.session_state.pop("alternatives", None)
        st.rerun()
    if pay:
        problems = _payment_problems(method, fields)
        for p in problems:
            st.error(p)
        if not problems:
            _submit(user, co, None if method == "Pay at counter" else
                    f"DEMO-{method.upper()}-{secrets.token_hex(3).upper()}")
    _show_alternatives(user)


def _payment_problems(method: str, fields: dict) -> list:
    """Format checks only, so the demo feels real; values are never kept."""
    if method == "Card":
        problems = []
        if not re.fullmatch(r"\d{12,19}", fields["card"].replace(" ", "")):
            problems.append("Enter a card number of 12 to 19 digits.")
        if not re.fullmatch(r"(0[1-9]|1[0-2])/\d{2}", fields["expiry"]):
            problems.append("Enter the expiry as MM/YY.")
        if not re.fullmatch(r"\d{3,4}", fields["cvv"]):
            problems.append("Enter the 3 or 4 digit CVV.")
        return problems
    if method == "UPI" and not re.fullmatch(r"[\w.\-]+@[\w.\-]+", fields["upi"].strip()):
        return ["Enter a UPI ID like name@bank."]
    return []


def _submit(user: dict, co: dict, payment_ref) -> None:
    lines = [{"item_id": line["item_id"], "quantity": line["quantity"]} for line in co["lines"]]
    st.session_state.pop("alternatives", None)
    common.run_action(
        ordering.submit_order, co["outlet_id"], co["slot"]["id"], user["campus_id"],
        user["display_name"], lines, payment_ref=payment_ref,
        success=_submitted_message, on_success=lambda result: _order_placed(user))
    # Reached only when the submit was refused (success reruns the script).
    slots = suggestions.next_available_slots(co["outlet_id"], co["slot"]["id"], lines)
    if slots:
        st.session_state["alternatives"] = slots


def _show_alternatives(user: dict) -> None:
    """Offer later slots where the whole order fits; picking one returns to checkout for it."""
    alternatives = st.session_state.get("alternatives")
    if not alternatives:
        return
    st.info("Your whole order fits in these later slots. Pick one to check out there instead.")
    for alt in alternatives:
        label = f"Use {clock.long_date(alt['date'])} · {alt['label']} instead"
        if st.button(label, key=f"alt_{alt['slot_id']}"):
            slot = next(s for s in queries.list_slots(alt["date"]) if s["id"] == alt["slot_id"])
            st.session_state["checkout"]["slot"] = slot
            st.session_state.pop("alternatives", None)
            st.rerun()


def _order_placed(user: dict) -> None:
    """Empty the saved cart; outlet and slot choices stay as the starting point."""
    common.forget(user["id"], "qty_")
    st.session_state.pop("checkout", None)
    st.session_state.pop("alternatives", None)


def _submitted_message(result: dict) -> str:
    text = (
        f"Order #{result['order_id']} placed. Pickup code: {result['pickup_code']} "
        "(keep it: you need it to cancel or collect). "
        f"Status: {result['status']}."
    )
    if result["payment_ref"]:
        text += f" Paid {_money(result['total'])} (demo, ref {result['payment_ref']})."
    else:
        text += f" Pay {_money(result['total'])} at the counter."
    if result["review_reason"]:
        text += f" Held for staff review ({result['review_reason']})."
    return text


def _my_orders(user: dict) -> None:
    st.subheader("My orders")
    customer_id = user["campus_id"]
    common.inbox(notifications.customer_key(customer_id), "Notifications")
    orders = queries.list_orders(customer_id=customer_id, viewer=CUSTOMER)
    if not orders:
        st.info("You have no orders yet.")
        return
    for o in orders:
        title = f"#{o['id']} · {o['outlet_name']} · {clock.long_date(o['date'])} {o['slot_label']}"
        with st.expander(f"{title} · {o['status']}", expanded=o["status"] not in CANCEL_BLOCKED):
            st.markdown(f"{common.badge(o['status'])} — {common.order_lines(o)}")
            st.caption(_payment_text(o))
            if o["status"] == "Pending Confirmation" and o["review_reason"]:
                st.caption(f"Waiting for staff review: {o['review_reason']}.")
            if o["closure_reason"] and o["status"] in (REJECTED, CANCELLED):
                st.warning(f"Reason: {o['closure_reason']}")
            common.timeline(o["history"])
            _cancel_control(o)


def _payment_text(o: dict) -> str:
    if not o["payment_ref"]:
        return f"Total {_money(o['total'])} · pay at the counter"
    text = f"Paid {_money(o['total'])} (demo) · ref {o['payment_ref']}"
    if o["status"] in (REJECTED, CANCELLED):
        text += " · refund issued (demo)"
    return text


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
