"""Shared Streamlit pieces: sidebar, error-safe actions, badges and the status timeline."""
from datetime import datetime

import streamlit as st

from core.rules import (
    BusinessRuleError, CANCELLED, COLLECTED, CONFIRMED, PENDING, PREPARING, READY, REJECTED,
)
from core.seed import reset_demo_data
from services import clock, notifications, queries

STATUS_COLOR = {
    PENDING: "orange", CONFIRMED: "blue", PREPARING: "violet", READY: "green",
    COLLECTED: "gray", REJECTED: "red", CANCELLED: "red",
}


def badge(status: str) -> str:
    return f":{STATUS_COLOR.get(status, 'gray')}[**{status}**]"


def show_flash() -> None:
    """Show the success message left by run_action before its rerun."""
    message = st.session_state.pop("flash", None)
    if message:
        st.success(message)


def run_action(fn, *args, success="Done.", on_success=None, **kwargs):
    """Call a service function; show refusals in place, or flash success and rerun.

    `success` is a string, or a function of the result returning a string.
    `on_success(result)` runs just before the rerun (e.g. to reset a form).
    """
    try:
        result = fn(*args, **kwargs)
    except BusinessRuleError as err:
        for line in err.lines:
            st.error(line)
        st.error(err.message)
        return None
    st.session_state["flash"] = success(result) if callable(success) else success
    if on_success:
        on_success(result)
    st.rerun()


def timeline(history: list) -> None:
    for h in history:
        step = f"{h['from_status'] or 'Submitted'} → **{h['to_status']}**"
        line = f"`{h['timestamp'][:16]}` {step} · {h['actor']}"
        if h["reason"]:
            line += f" — {h['reason']}"
        st.markdown(f"- {line}")


def order_lines(order: dict) -> str:
    return ", ".join(f"{line['quantity']} × {line['name']}" for line in order["lines"])


def sidebar(roles: list) -> tuple:
    """Role, outlet (staff and manager only), app clock and reset. Returns (role, ctx)."""
    with st.sidebar:
        st.header("Campus Food Pre-Order")
        role = st.radio("View as", roles)
        outlet_id = None
        if role in ("Outlet Staff", "Outlet Manager"):
            outlets = {o["name"]: o["id"] for o in queries.list_outlets()}
            outlet_id = outlets[st.selectbox("Outlet", list(outlets))]

        st.divider()
        now = clock.current_now()
        st.caption(f"App clock: {clock.long_date(now.strftime('%Y-%m-%d'))}, {now:%H:%M}")
        stamp = now.strftime("%Y%m%d%H%M")  # new widget keys follow clock changes
        day = st.date_input("Date", value=now.date(), key=f"clock_date_{stamp}")
        time = st.time_input("Time", value=now.time(), key=f"clock_time_{stamp}", step=300)
        if st.button("Set app clock"):
            run_action(clock.set_now, datetime.combine(day, time), success="App clock updated.")
        if st.button("Reset demo data"):
            reset_demo_data()
            st.session_state["flash"] = "Demo data reset to the seed state."
            st.rerun()
    return role, {"outlet_id": outlet_id, "now": now}


def inbox(recipient: str, title: str = "Notifications") -> None:
    """Unread badge, toasts for messages not yet shown this session, and the message list."""
    seen_key = f"toast_seen_{recipient}"
    messages = notifications.inbox(recipient)
    newest = messages[0]["id"] if messages else 0
    if seen_key not in st.session_state:
        st.session_state[seen_key] = newest  # do not replay history on first view
    for m in reversed(messages):
        if m["id"] > st.session_state[seen_key]:
            st.toast(m["message"])
    st.session_state[seen_key] = max(st.session_state[seen_key], newest)

    unread = sum(1 for m in messages if not m["is_read"])
    label = f"{title} ({unread} unread)" if unread else title
    with st.expander(label, expanded=bool(unread)):
        if not messages:
            st.caption("No notifications yet.")
        for m in messages:
            marker = ":blue[●] " if not m["is_read"] else ""
            st.markdown(f"{marker}`{m['created_at'][5:16]}` {m['message']}")
        if unread and st.button("Mark all read", key=f"read_{recipient}"):
            notifications.mark_all_read(recipient)
            st.rerun()
