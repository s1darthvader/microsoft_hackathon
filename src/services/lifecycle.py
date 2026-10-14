"""The order state machine (BR-10 .. BR-16, V-08 .. V-12, FR-X2).

All legality comes from core.rules.TRANSITIONS; nothing is scattered in the UI.
"""
from core.db import tx
from core.rules import (
    BusinessRuleError, CANCELLED, COLLECTED, CUSTOMER, PREPARING, READY,
    REJECTED, TERMINAL, TRANSITIONS,
)
from services import clock, notifications

_VERB = {
    "auto_confirm": "confirmed", "confirm": "confirmed", "reject": "rejected",
    "cancel": "cancelled", "outlet_cancel": "cancelled",
    "start_preparation": "started", "mark_ready": "marked ready",
    "mark_collected": "collected",
}


def allowed_actions(status, actor) -> list:
    """Actions `actor` may take on an order in `status` (drives the UI buttons)."""
    return [a for a, t in TRANSITIONS.get(status, {}).items() if actor in t.actors]


def record_history(conn, order_id, from_status, to_status, actor, reason=None) -> None:
    conn.execute(
        "INSERT INTO order_status_history (order_id, from_status, to_status, actor, reason, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (order_id, from_status, to_status, actor, reason, clock.now_str(conn)))


def _load(conn, order_id):
    row = conn.execute(
        "SELECT o.*, s.date, s.start_time, s.end_time FROM orders o "
        "JOIN pickup_slot s ON s.id = o.slot_id WHERE o.id = ?", (order_id,)).fetchone()
    if row is None:
        raise BusinessRuleError(f"Order #{order_id} was not found.")
    return row


def _check_confirmable(conn, order) -> None:
    """BR-10: flags and timing only. Quantity was reserved at submit, never re-check it."""
    if clock.get_now(conn) >= clock.slot_end(order):
        raise BusinessRuleError(
            f"Cannot confirm: the {clock.slot_label(order)} slot has already ended. "
            "Reject this pre-order with a reason.")
    flagged = conn.execute(
        "SELECT m.name, a.unavailable_reason FROM order_line l "
        "JOIN slot_item_availability a ON a.item_id = l.item_id AND a.slot_id = ? "
        "JOIN menu_item m ON m.id = l.item_id "
        "WHERE l.order_id = ? AND a.is_unavailable = 1", (order["slot_id"], order["id"])).fetchall()
    if flagged:
        parts = "; ".join(f"{r['name']} is now unavailable ({r['unavailable_reason']})" for r in flagged)
        raise BusinessRuleError(f"Cannot confirm: {parts}. Reject this pre-order with a reason.")


def _illegal(order, action) -> BusinessRuleError:
    status = order["status"]
    if action == "cancel" and status in (PREPARING, READY, COLLECTED):
        return BusinessRuleError(
            "Preparation has already started, so this order can no longer be cancelled.")
    repeat = status in TERMINAL and any(
        rules[action].to == status for rules in TRANSITIONS.values() if action in rules)
    suffix = " again" if repeat else ""
    return BusinessRuleError(
        f"Order #{order['id']} is {status}; it cannot be {_VERB.get(action, action)}{suffix}.")


def apply_transition(conn, order_id, action, actor, reason=None, pickup_code=None) -> dict:
    """Run one transition inside the caller's transaction."""
    order = _load(conn, order_id)
    rule = TRANSITIONS.get(order["status"], {}).get(action)
    if rule is None:
        raise _illegal(order, action)
    if actor not in rule.actors:
        raise BusinessRuleError(f"Order #{order_id}: {actor} cannot perform {action}.")
    reason = (reason or "").strip() or None
    if rule.needs_reason and reason is None:
        raise BusinessRuleError("A reason is required.")
    if rule.needs_code and (pickup_code or "").strip() != order["pickup_code"]:
        raise BusinessRuleError(f"The pickup code does not match order #{order_id}.")
    if action in ("confirm", "auto_confirm"):
        _check_confirmable(conn, order)

    closure = None
    if rule.to in (REJECTED, CANCELLED):
        closure = reason or ("Cancelled by customer" if actor == CUSTOMER else None)
    conn.execute(
        "UPDATE orders SET status = ?, closure_reason = COALESCE(?, closure_reason) WHERE id = ?",
        (rule.to, closure, order_id))
    record_history(conn, order_id, order["status"], rule.to, actor, reason)
    notifications.on_transition(conn, order, rule.to, actor, reason)
    return {"order_id": order_id, "status": rule.to}


def transition(order_id, action, actor, reason=None, pickup_code=None) -> dict:
    """The single public entry point for every status change."""
    with tx() as conn:
        return apply_transition(conn, order_id, action, actor, reason, pickup_code)
