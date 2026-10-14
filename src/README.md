# Campus Food Pre-Order and Pickup

Implementation of `docs/requirements and design/campus-food-preorder-requirements-v2.md`.

## Run

From the repository root:

```bash
pip install -r src/requirements.txt
streamlit run src/app.py
pytest src/tests
```

Data lives in `src/campus_food.db` and survives restarts. An older database is reseeded
automatically when the schema version changes. Use **Reset demo data** (sidebar, *Demo tools*)
to return to the seed state; it also signs you out. The **app clock** (sidebar) starts at 4 Aug 2026 10:00
and drives slot cut-offs and every timestamp.

## Sign in

Every stakeholder signs in; the role, and for staff and managers the outlet, come from the
account. All demo accounts use the password `demo123`:

| Username | Role | Outlet |
| --- | --- | --- |
| `student1`, `student2` | Customer (campus IDs S101, S102) | |
| `canteen.staff`, `kiosk.staff` | Outlet Staff | Main Canteen, Snack Kiosk |
| `canteen.mgr`, `kiosk.mgr` | Outlet Manager | Main Canteen, Snack Kiosk |
| `admin` | Campus Admin | |

Passwords are PBKDF2-hashed (`core/passwords.py`, `services/auth.py`). A browser refresh starts a
new Streamlit session, so you sign in again; your drafts are restored.

## Drafts and demo payment

- **Drafts** (`services/drafts.py`, `ui/common.persist`): the customer's outlet, date, slot and
  quantities, and a staff member's typed reject/cancel reasons, are saved per user on every
  change and restored after sign-out, refresh or a slot change. A placed order clears the
  quantities; a reject or outlet cancel clears that order's reason.
- **Checkout** (`ui/customer._checkout`): *Review & pay* shows the priced order and a mock Card /
  UPI / Pay-at-counter form with format checks only. No money moves and payment details are
  never stored; the order keeps only a `DEMO-...` reference (`orders.payment_ref`). Stock is
  still checked when you pay, and a refused order offers later slots that return to checkout.

## Layout

```
app.py        entry point: sign-in gate, sidebar, role router
core/         rules.py (statuses, TRANSITIONS table, BusinessRuleError)
              db.py (connections, BEGIN IMMEDIATE tx)  seed.py (seed data, users, init, reset)
              passwords.py (PBKDF2 hashing)
services/     business logic, one module per area, no UI imports
ui/           Streamlit pages, call services only
tests/        one test per acceptance scenario (AT-01 .. AT-18) plus edge cases
```

Dependency direction is `ui -> services -> core`. Every status change goes through
`services.lifecycle.transition`, driven by the one table in `core/rules.py`.

## Rule traceability

| Rule | Enforced in | Tested by |
| --- | --- | --- |
| BR-02 one outlet per order | `ordering._check_one_outlet` | AT-16 |
| BR-03 derived availability | `availability._ITEM_SQL` | seed test, AT-05, AT-18 |
| BR-04 all-or-nothing submit | `ordering._check_availability` | AT-02, AT-03 |
| BR-05 atomic check-and-reserve | `db.tx` (BEGIN IMMEDIATE) | AT-12 |
| BR-08, BR-09 hybrid confirmation | `ordering.submit_order` | AT-01, AT-07, AT-14 |
| BR-10 confirm checks flags, not quantity | `lifecycle._check_confirmable` | AT-11, AT-17 |
| BR-11 reject is terminal, releases stock | `TRANSITIONS`, `COUNTED` | AT-07 |
| BR-12, BR-14 customer cancel | `TRANSITIONS`, `lifecycle._illegal` | AT-08, AT-09 |
| BR-13 outlet cancel with reason | `TRANSITIONS` | AT-15 |
| BR-15, BR-16 forward-only, collect needs code | `TRANSITIONS` | AT-01, AT-10 |
| BR-17, BR-18 availability flags, Affected | `menu.set_unavailable`, `queries.list_orders` | AT-04, AT-11, AT-15 |
| BR-19 sold out derived | `availability._shape` | AT-06 |
| BR-20 capacity floor | `menu.set_capacity` | `test_manager.py` |
| BR-21 slot cut-off on app clock | `ordering.submit_order` | AT-13 |

## Assumptions kept from the spec

A3 app clock, A7 Collected keeps counting, A9 hybrid confirmation (threshold 10),
A13 outlet cancel only from Confirmed.

## Status

Built and tested: all Must requirements, FR-M2, FR-M3, FR-M4, FR-A1, FR-S5, and the in-app
notifications bonus (section 12): customer and outlet inboxes with an unread badge and toasts,
written in the same transaction as the change they describe (`services/notifications.py`,
`tests/test_notifications.py`).

Also built: the "next available slot" suggestion bonus (`services/suggestions.py`). It only
advises; booking a suggested slot re-runs the full `submit_order` validation.

Changed from the spec: A4 (no auth) is replaced by per-stakeholder sign-in; the pickup code is
still required to cancel or collect, is shown once at submit and is never returned by queries.
A10 (no payment) is relaxed to prices plus a demo checkout that takes no money.

Not built: real payments or refunds, account management (creating users, changing passwords),
editing a submitted pre-order, no-show handling.
