"""Shared Streamlit pieces: session user, sidebar, drafts, error-safe actions, badges, timeline."""
from datetime import datetime

import streamlit as st

from core.rules import (
    BusinessRuleError, CANCELLED, COLLECTED, CONFIRMED, PENDING, PREPARING, READY, REJECTED,
)
from core.seed import reset_demo_data
from services import auth, clock, drafts, notifications

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


def current_user():
    """The signed-in user, re-read each run so a reset elsewhere signs this session out."""
    user = st.session_state.get("user")
    if user is None:
        return None
    fresh = auth.get_user(user["id"])
    if fresh is None or fresh["username"] != user["username"]:
        st.session_state.clear()
        return None
    st.session_state["user"] = fresh
    return fresh


def sign_out(flash: str) -> None:
    """Drop all session state (drafts stay in the database) and return to the login screen."""
    st.session_state.clear()
    st.session_state["flash"] = flash
    st.rerun()


def persist(user_id: int, key: str, default, options=None) -> dict:
    """Widget kwargs that restore `key` from the user's draft and save it on every change.

    Use as `st.text_input("Reason", **persist(uid, "reason_7", ""))`. When `options`
    is given, a stored value that is no longer offered falls back to `default`.
    """
    value = st.session_state.get(key)
    if key not in st.session_state:
        value = drafts.load(user_id, key, default)
    if options is not None and value not in options:
        value = default
    if key not in st.session_state or st.session_state[key] != value:
        st.session_state[key] = value

    def save():
        drafts.save(user_id, key, st.session_state[key])

    return {"key": key, "on_change": save}


def forget(user_id: int, prefix: str) -> None:
    """Clear drafts and widget state whose key starts with `prefix`."""
    drafts.clear_prefix(user_id, prefix)
    for key in [k for k in st.session_state if k.startswith(prefix)]:
        del st.session_state[key]


def sidebar(user: dict) -> dict:
    """Signed-in user, sign out, app clock and reset. Returns the page ctx."""
    with st.sidebar:
        st.header("Campus Food Pre-Order")
        st.markdown(f"Signed in as **{user['display_name']}** (`{user['username']}`)")
        st.caption(user["role"] + (f" · {user['outlet_name']}" if user["outlet_name"] else ""))
        if st.button("Sign out"):
            sign_out("Signed out. Your unfinished cart and notes are saved for next time.")

        st.divider()
        now = clock.current_now()
        with st.expander("Demo tools"):
            st.caption(f"App clock: {clock.long_date(now.strftime('%Y-%m-%d'))}, {now:%H:%M}")
            stamp = now.strftime("%Y%m%d%H%M")  # new widget keys follow clock changes
            day = st.date_input("Date", value=now.date(), key=f"clock_date_{stamp}")
            time = st.time_input("Time", value=now.time(), key=f"clock_time_{stamp}", step=300)
            if st.button("Set app clock"):
                run_action(clock.set_now, datetime.combine(day, time), success="App clock updated.")
            if st.button("Reset demo data"):
                reset_demo_data()
                sign_out("Demo data reset to the seed state. Please sign in again.")
    return {"user": user, "outlet_id": user["outlet_id"], "now": now}


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
