"""Outlet staff view: review queue, preparation flow, outlet cancellation (FR-S1 .. FR-S5)."""
from itertools import groupby

import streamlit as st

from core.rules import CONFIRMED, PENDING, PREPARING, READY, STAFF, STATUSES
from services import clock, lifecycle, notifications, queries
from ui import common

ACTION_LABEL = {
    "confirm": "Confirm",
    "reject": "Reject",
    "start_preparation": "Start preparation",
    "mark_ready": "Mark ready",
    "mark_collected": "Mark collected",
    "outlet_cancel": "Cancel by outlet",
}
SUCCESS = {
    "confirm": "confirmed", "reject": "rejected", "start_preparation": "moved to Preparing",
    "mark_ready": "marked Ready", "mark_collected": "collected", "outlet_cancel": "cancelled",
}
ACTIVE = [PENDING, CONFIRMED, PREPARING, READY]


def render(ctx: dict) -> None:
    outlet_id = ctx["outlet_id"]
    common.inbox(notifications.outlet_key(outlet_id), "Outlet notifications")
    find_col, filter_col = st.columns([1, 3])
    number = find_col.number_input("Find order number", min_value=0, step=1, value=0)
    shown = filter_col.multiselect("Show statuses", STATUSES, default=ACTIVE)

    orders = queries.list_orders(outlet_id=outlet_id, viewer=STAFF)
    if number:
        orders = [o for o in orders if o["id"] == number]
        if not orders:
            st.info(f"Order #{number} was not found at this outlet.")
    else:
        orders = [o for o in orders if o["status"] in shown]
    if not orders:
        st.caption("Nothing in the queue for these filters.")
        return

    for (date, label), group in groupby(orders, key=lambda o: (o["date"], o["slot_label"])):
        st.subheader(f"{clock.long_date(date)} · {label}")
        for o in group:
            _order_card(o)


def _flags(o: dict) -> str:
    parts = []
    if o["needs_review"]:
        parts.append(f":orange[Needs review: {o['review_reason']}]")
    if o["affected"]:
        parts.append(f":red[Affected: {', '.join(o['flagged_items'])}]")
    if o["overdue"]:
        parts.append(":violet[Overdue: slot has ended]")
    return " · ".join(parts)


def _order_card(o: dict) -> None:
    with st.container(border=True):
        st.markdown(
            f"**#{o['id']}** · {o['customer_name']} ({o['customer_id']}) · "
            f"{common.badge(o['status'])}")
        st.write(common.order_lines(o))
        flags = _flags(o)
        if flags:
            st.markdown(flags)
        if o["closure_reason"]:
            st.caption(f"Reason: {o['closure_reason']}")
        with st.expander("Timeline"):
            common.timeline(o["history"])

        actions = [a for a in o["allowed_actions"] if a in ACTION_LABEL]
        if not actions:
            return
        reason = code = None
        if "reject" in actions or "outlet_cancel" in actions:
            reason = st.text_input("Reason", key=f"reason_{o['id']}")
        if "mark_collected" in actions:
            code = st.text_input("Customer pickup code", key=f"code_{o['id']}", max_chars=4)
        for col, action in zip(st.columns(len(actions)), actions):
            if col.button(ACTION_LABEL[action], key=f"{action}_{o['id']}"):
                common.run_action(
                    lifecycle.transition, o["id"], action, STAFF, reason=reason, pickup_code=code,
                    success=f"Order #{o['id']} {SUCCESS[action]}.")
