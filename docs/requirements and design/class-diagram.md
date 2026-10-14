# Class diagrams (high level)

The implementation is function-oriented: the only real Python classes are `BusinessRuleError`
and the `Transition` named tuple. Domain data travels as SQLite rows and plain `dict`s, and
behaviour lives in modules. These diagrams therefore show two views:

1. **Domain model**: the entities and value types the system manipulates (backed by tables).
2. **Module model**: each module drawn as a class with its public operations, plus the two
   real classes. Modules are tagged `<<module>>`.

See also: [Architecture](architecture.md) · [System capabilities](capabilities.md) ·
[Testing](testing.md)

## 1. Domain model

```mermaid
classDiagram
    direction LR

    class Outlet {
        +int id
        +str name
        +bool auto_confirm
        +int bulk_review_threshold
    }
    class MenuItem {
        +int id
        +str name
        +str category
        +int default_qty_per_slot
    }
    class PickupSlot {
        +int id
        +str date
        +str start_time
        +str end_time
    }
    class SlotItemAvailability {
        +int capacity
        +bool is_unavailable
        +str unavailable_reason
    }
    class Order {
        +int id
        +str customer_id
        +str customer_name
        +OrderStatus status
        +str pickup_code
        +str review_reason
        +str closure_reason
        +str created_at
    }
    class OrderLine {
        +int quantity
    }
    class OrderStatusHistory {
        +OrderStatus from_status
        +OrderStatus to_status
        +Actor actor
        +str reason
        +str timestamp
    }
    class Notification {
        +str recipient
        +str message
        +str created_at
        +bool is_read
    }
    class ItemAvailability {
        <<derived>>
        +int capacity
        +int counted
        +int available
        +AvailabilityState state
        +str reason
    }
    class OrderStatus {
        <<enumeration>>
        PENDING
        CONFIRMED
        PREPARING
        READY
        COLLECTED
        REJECTED
        CANCELLED
    }
    class Actor {
        <<enumeration>>
        CUSTOMER
        STAFF
        SYSTEM
    }
    class AvailabilityState {
        <<enumeration>>
        available
        sold_out
        unavailable
    }

    Outlet "1" --> "*" MenuItem : sells
    Outlet "1" --> "*" Order : receives
    PickupSlot "1" --> "*" Order : pickup window of
    PickupSlot "1" --> "*" SlotItemAvailability : has
    MenuItem "1" --> "*" SlotItemAvailability : offered per slot
    Order "1" *-- "1..*" OrderLine : contains
    MenuItem "1" --> "*" OrderLine : ordered as
    Order "1" *-- "*" OrderStatusHistory : audit trail
    Order "1" --> "*" Notification : triggers
    SlotItemAvailability ..> ItemAvailability : computed with COUNTED order lines
    Order ..> OrderStatus
    OrderStatusHistory ..> Actor
    ItemAvailability ..> AvailabilityState
```

Notes on the model:

- `ItemAvailability` is derived and never stored. It is computed on every read: `available = 0` if flagged, otherwise
  `max(capacity - counted, 0)`, where `counted` sums line quantities over orders in a COUNTED
  status. Its `state` is `unavailable` when flagged, `sold_out` when `available == 0`, else `available`.
- `OrderStatus` string values are `Pending Confirmation`, `Confirmed`, `Preparing`, `Ready`,
  `Collected`, `Rejected`, `Cancelled`. `Collected`, `Rejected` and `Cancelled` are terminal.
- `Notification.recipient` is a string key (`customer:<campus id>` or `outlet:<outlet id>`),
  not a foreign key, and `order_id` may be empty.
- A `Customer` is not an entity: orders carry `customer_id` (campus ID) and `customer_name` directly.

## 2. Module model

Dependency arrows (`..>`) read "uses". Every `services` module also uses `db` and `rules`;
those edges are omitted except where they define the module's purpose.

```mermaid
classDiagram
    direction TB

    class app {
        <<module>>
        +PAGES dict
    }

    class ui_common {
        <<module>>
        +sidebar(roles) tuple
        +run_action(fn, args, success)
        +inbox(recipient, title)
        +timeline(history)
        +badge(status) str
        +show_flash()
    }
    class ui_customer {
        <<module>>
        +render(ctx)
        -_place_order()
        -_my_orders()
        -_cancel_control(order)
    }
    class ui_staff {
        <<module>>
        +render(ctx)
        -_order_card(order)
    }
    class ui_manager {
        <<module>>
        +render(ctx)
        -_flag_form(outlet_id, items, dates)
        -_policy_form(outlet)
        -_demand(outlet_id, dates)
    }
    class ui_admin {
        <<module>>
        +render(ctx)
    }

    class ordering {
        <<module>>
        +submit_order(outlet_id, slot_id, customer_id, customer_name, lines) dict
        +normalise_lines(lines) dict
    }
    class lifecycle {
        <<module>>
        +transition(order_id, action, actor, reason, pickup_code) dict
        +apply_transition(conn, order_id, action, actor, reason, pickup_code) dict
        +allowed_actions(status, actor) list
        +record_history(conn, order_id, from_status, to_status, actor, reason)
    }
    class availability {
        <<module>>
        +get_availability(outlet_id, slot_id) list
        +slot_item(conn, slot_id, item_id) dict
        +slot_items(conn, slot_id, outlet_id) list
        +slot_demand(outlet_id, date) list
    }
    class menu {
        <<module>>
        +set_unavailable(outlet_id, item_id, date, slot_id, flagged, reason) int
        +set_outlet_policy(outlet_id, auto_confirm, bulk_threshold)
        +set_capacity(outlet_id, slot_id, item_id, new_capacity)
    }
    class queries {
        <<module>>
        +list_orders(customer_id, outlet_id, status, order_id, viewer) list
        +get_order(order_id, viewer) dict
        +list_outlets() list
        +list_dates() list
        +list_slots(date) list
        +list_items(outlet_id) list
    }
    class notifications {
        <<module>>
        +on_transition(conn, order, to_status, actor, reason)
        +on_review_needed(conn, order_id, outlet_id, review_reason)
        +on_flag(conn, outlet_id, item_name, affected)
        +inbox(recipient, limit) list
        +unread_count(recipient) int
        +mark_all_read(recipient)
    }
    class suggestions {
        <<module>>
        +next_available_slots(outlet_id, slot_id, lines, limit) list
    }
    class clock {
        <<module>>
        +get_now(conn) datetime
        +current_now() datetime
        +set_now(value)
        +slot_start(slot) datetime
        +slot_end(slot) datetime
        +slot_label(slot) str
    }

    class rules {
        <<module>>
        +STATUSES
        +COUNTED
        +TERMINAL
        +TRANSITIONS
        +UNAVAILABLE_REASONS
    }
    class Transition {
        <<namedtuple>>
        +to
        +actors
        +needs_reason
        +needs_code
    }
    class BusinessRuleError {
        <<exception>>
        +message str
        +lines list
    }
    class db {
        <<module>>
        +connect() Connection
        +read() Connection
        +tx() Connection
        +create_schema(conn)
        +drop_schema(conn)
    }
    class seed {
        <<module>>
        +seed(conn)
        +init_db()
        +reset_demo_data()
    }

    app ..> ui_common
    app ..> ui_customer
    app ..> ui_staff
    app ..> ui_manager
    app ..> ui_admin
    app ..> seed

    ui_customer ..> ui_common
    ui_staff ..> ui_common
    ui_manager ..> ui_common
    ui_common ..> queries
    ui_common ..> notifications
    ui_common ..> clock
    ui_common ..> seed

    ui_customer ..> ordering
    ui_customer ..> lifecycle
    ui_customer ..> suggestions
    ui_customer ..> availability
    ui_staff ..> lifecycle
    ui_staff ..> queries
    ui_manager ..> menu
    ui_manager ..> availability
    ui_manager ..> queries
    ui_admin ..> availability
    ui_admin ..> queries

    ordering ..> availability
    ordering ..> lifecycle
    ordering ..> notifications
    lifecycle ..> notifications
    lifecycle ..> rules
    menu ..> availability
    menu ..> notifications
    queries ..> lifecycle
    suggestions ..> ordering
    suggestions ..> availability
    notifications ..> clock
    availability ..> rules
    availability ..> db
    clock ..> db
    seed ..> db

    rules *-- Transition : defines
    rules *-- BusinessRuleError : defines
```

Every `services` module raises `BusinessRuleError` for a refused action; `ui_common.run_action`
catches it and shows `message` and each entry of `lines` in place.

### How the pieces map to the domain

| Domain concept | Owned by (writes) | Read through |
| --- | --- | --- |
| Order, OrderLine, OrderStatusHistory | `ordering` (create), `lifecycle` (status changes) | `queries.list_orders` |
| SlotItemAvailability (capacity, flags) | `menu` | `availability` |
| ItemAvailability (derived) | none, computed | `availability.slot_item(s)`, `get_availability`, `slot_demand` |
| Outlet policy (auto-confirm, threshold) | `menu.set_outlet_policy` | `queries.list_outlets` |
| Notification | `notifications` (inside the caller's transaction) | `notifications.inbox` |
| App clock (`app_setting`) | `clock.set_now`, `seed` | `clock.get_now`, `clock.current_now` |
| Outlet, MenuItem, PickupSlot | `seed` only (no UI to create them, A11) | `queries.list_*` |
