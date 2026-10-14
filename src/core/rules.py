"""Statuses, actors, the transition table (spec section 4) and the one error type."""
from collections import namedtuple

PENDING = "Pending Confirmation"
CONFIRMED = "Confirmed"
PREPARING = "Preparing"
READY = "Ready"
COLLECTED = "Collected"
REJECTED = "Rejected"
CANCELLED = "Cancelled"

STATUSES = (PENDING, CONFIRMED, PREPARING, READY, COLLECTED, REJECTED, CANCELLED)
# Statuses whose quantities count against slot capacity. Only REJECTED and
# CANCELLED release stock; COLLECTED keeps consuming it (assumption A7).
COUNTED = (PENDING, CONFIRMED, PREPARING, READY, COLLECTED)
TERMINAL = (COLLECTED, REJECTED, CANCELLED)

CUSTOMER = "Customer"
STAFF = "Staff"
SYSTEM = "System"

UNAVAILABLE_REASONS = (
    "Sold out",
    "Cannot be prepared",
    "Ingredient shortage",
    "Operational restriction",
)

Transition = namedtuple("Transition", "to actors needs_reason needs_code")

# {status: {action: Transition}}. Availability is derived from status, so there
# is no "releases stock" column: leaving COUNTED is what releases stock.
TRANSITIONS = {
    PENDING: {
        "auto_confirm": Transition(CONFIRMED, (SYSTEM,), False, False),
        "confirm": Transition(CONFIRMED, (STAFF,), False, False),
        "reject": Transition(REJECTED, (STAFF,), True, False),
        "cancel": Transition(CANCELLED, (CUSTOMER,), False, True),
    },
    CONFIRMED: {
        "start_preparation": Transition(PREPARING, (STAFF,), False, False),
        "cancel": Transition(CANCELLED, (CUSTOMER,), False, True),
        "outlet_cancel": Transition(CANCELLED, (STAFF,), True, False),
    },
    PREPARING: {
        "mark_ready": Transition(READY, (STAFF,), False, False),
    },
    READY: {
        "mark_collected": Transition(COLLECTED, (STAFF,), False, True),
    },
}


class BusinessRuleError(Exception):
    """A refused action. `message` is user-facing; `lines` lists each failing line."""

    def __init__(self, message, lines=None):
        super().__init__(message)
        self.message = message
        self.lines = list(lines or [])

    def __str__(self):
        return "\n".join([*self.lines, self.message])
