# Architecture

Campus Food Pre-Order and Pickup is a single-process Streamlit application over one SQLite
file. The code in `src/` is split into three layers with a strict one-way dependency:
`ui -> services -> core`. All business rules live in `services/` and `core/`; the UI only
renders state and forwards user actions.

See also: [System capabilities](capabilities.md) · [Class diagram](class-diagram.md) ·
[Testing](testing.md) · [Requirements v2](requirements%20and%20design/campus-food-preorder-requirements-v2.md)

## 1. Layered view

```mermaid
flowchart TB
    users["Customer · Outlet Staff<br/>Outlet Manager · Campus Admin<br/>(signed in; role and outlet from the account)"]

    subgraph proc["Streamlit process"]
        app["app.py<br/>init_db, sign-in gate, role router"]
        ui["ui/ presentation<br/>login · customer · staff<br/>manager · admin · common"]
        services["services/ business logic<br/>ordering · lifecycle · availability<br/>menu · queries · notifications<br/>suggestions · clock · auth · drafts"]
        core["core/ rules and persistence<br/>rules · db · seed · passwords"]
    end

    file[("SQLite file<br/>src/campus_food.db")]

    users --> app
    app --> ui
    ui -->|"calls services only"| services
    services -->|"uses"| core
    core -->|"one connection<br/>per operation"| file
```

| Layer | Responsibility | Must not |
| --- | --- | --- |
| `ui/` | Streamlit pages per role, forms, buttons, toasts. Shows `BusinessRuleError` messages in place. | Contain rules or SQL. |
| `services/` | Validation, availability, state transitions, notifications, read models. One module per area. | Import Streamlit. |
| `core/` | Status constants and the transition table, SQLite connections and transactions, seed data. | Know about pages or services. |

## 2. Module dependencies

Arrows read "imports / calls". Every service module also uses `core.db` and `core.rules`;
those edges are drawn once from the group to keep the diagram readable.

```mermaid
flowchart LR
    subgraph ui["ui/"]
        u_common["common"]
        u_login["login"]
        u_customer["customer"]
        u_staff["staff"]
        u_manager["manager"]
        u_admin["admin"]
    end

    subgraph services["services/"]
        s_ordering["ordering"]
        s_lifecycle["lifecycle"]
        s_availability["availability"]
        s_menu["menu"]
        s_queries["queries"]
        s_notifications["notifications"]
        s_suggestions["suggestions"]
        s_clock["clock"]
        s_auth["auth"]
        s_drafts["drafts"]
    end

    subgraph core["core/"]
        c_rules["rules"]
        c_db["db"]
        c_seed["seed"]
        c_passwords["passwords"]
    end

    u_customer --> u_common
    u_staff --> u_common
    u_manager --> u_common
    u_common --> s_clock
    u_common --> s_queries
    u_common --> s_notifications
    u_common --> c_seed
    u_common --> s_auth
    u_common --> s_drafts
    u_login --> s_auth
    u_staff --> s_drafts
    s_auth --> c_passwords
    s_drafts --> s_clock
    c_seed --> c_passwords

    u_customer --> s_ordering
    u_customer --> s_lifecycle
    u_customer --> s_suggestions
    u_customer --> s_availability
    u_staff --> s_lifecycle
    u_staff --> s_queries
    u_manager --> s_menu
    u_manager --> s_availability
    u_manager --> s_queries
    u_admin --> s_availability
    u_admin --> s_queries

    s_ordering --> s_availability
    s_ordering --> s_lifecycle
    s_ordering --> s_notifications
    s_ordering --> s_clock
    s_lifecycle --> s_notifications
    s_lifecycle --> s_clock
    s_menu --> s_availability
    s_menu --> s_notifications
    s_queries --> s_lifecycle
    s_queries --> s_clock
    s_suggestions --> s_ordering
    s_suggestions --> s_availability
    s_suggestions --> s_clock
    s_notifications --> s_clock

    services --> c_db
    services --> c_rules
    ui --> c_rules
    c_seed --> c_db
    c_seed --> c_rules
```

## 3. Order state machine

Every status change goes through `services.lifecycle.transition`, which looks the action up in
the single `TRANSITIONS` table in `core/rules.py`. The UI derives its buttons from
`lifecycle.allowed_actions(status, actor)`, so there is no transition logic in page code.

```mermaid
stateDiagram-v2
    state "Pending Confirmation" as Pending

    [*] --> Pending : submit (Customer)
    Pending --> Confirmed : auto_confirm (System)
    Pending --> Confirmed : confirm (Staff)
    Pending --> Rejected : reject (Staff, reason)
    Pending --> Cancelled : cancel (Customer, pickup code)
    Confirmed --> Preparing : start_preparation (Staff)
    Confirmed --> Cancelled : cancel (Customer, pickup code)
    Confirmed --> Cancelled : outlet_cancel (Staff, reason)
    Preparing --> Ready : mark_ready (Staff)
    Ready --> Collected : mark_collected (Staff, pickup code)
    Rejected --> [*]
    Cancelled --> [*]
    Collected --> [*]
```

Stock accounting follows from the status alone. `COUNTED` statuses (Pending Confirmation,
Confirmed, Preparing, Ready, Collected) use up slot capacity; entering Rejected or Cancelled
releases it. Collected keeps counting (assumption A7).

## 4. Runtime flows

### 4.1 Submit a pre-order

`submit_order` is one `BEGIN IMMEDIATE` transaction: it takes the write lock before the first
read, so two concurrent submits cannot both see the same last unit (BR-05).

```mermaid
sequenceDiagram
    actor C as Customer
    participant UI as ui.customer
    participant RA as ui.common.run_action
    participant O as services.ordering
    participant A as services.availability
    participant L as services.lifecycle
    participant N as services.notifications
    participant DB as core.db.tx (SQLite)

    C->>UI: Pay on demo checkout (outlet, slot, quantities; campus ID and name from the account)
    UI->>RA: run_action(submit_order, ...)
    RA->>O: submit_order(...)
    O->>O: check identity, normalise_lines (V-01, V-02)
    O->>DB: BEGIN IMMEDIATE
    O->>O: one outlet only, slot not started (BR-02, BR-21)
    O->>A: slot_item for every line (derived availability)
    alt any line unavailable, sold out or over-asked
        O-->>DB: ROLLBACK
        O-->>RA: BusinessRuleError listing every failing line
        RA-->>C: errors shown, nothing reserved
        UI->>UI: suggestions.next_available_slots (advice only)
    else every line fits
        O->>DB: INSERT order (Pending), order lines, history
        alt auto-confirm on and total quantity within threshold
            O->>L: apply_transition(auto_confirm, System)
            L->>N: on_transition (customer notified)
        else bulk order or manual confirmation
            O->>N: on_review_needed (outlet notified)
        end
        O->>DB: COMMIT
        O-->>RA: order_id, pickup_code, status
        RA-->>C: success message, rerun
    end
```

### 4.2 Staff or customer action on an existing order

```mermaid
sequenceDiagram
    actor U as Staff or Customer
    participant UI as ui page
    participant L as services.lifecycle
    participant R as core.rules.TRANSITIONS
    participant N as services.notifications
    participant DB as core.db.tx (SQLite)

    U->>UI: Click action (confirm, reject, mark ready, cancel, ...)
    UI->>L: transition(order_id, action, actor, reason, pickup_code)
    L->>DB: BEGIN IMMEDIATE
    L->>R: TRANSITIONS[status][action]
    alt no such transition, wrong actor, missing reason, wrong code
        L-->>DB: ROLLBACK
        L-->>UI: BusinessRuleError (shown in place)
    else legal
        opt confirm or auto_confirm
            L->>L: _check_confirmable (flags and slot end, never quantity)
        end
        L->>DB: UPDATE orders.status, INSERT order_status_history
        L->>N: on_transition (same transaction)
        L->>DB: COMMIT
        L-->>UI: order_id, new status
    end
```

## 5. Data model

Availability is **not** stored. It is computed on every read as
`0 if flagged else capacity - SUM(quantity over COUNTED orders)` from `slot_item_availability`
and `order_line`, so the figure cannot drift (BR-03).

```mermaid
erDiagram
    outlet ||--o{ menu_item : sells
    outlet ||--o{ orders : receives
    pickup_slot ||--o{ slot_item_availability : "capacity per item"
    menu_item ||--o{ slot_item_availability : "offered in"
    pickup_slot ||--o{ orders : "pickup window"
    orders ||--|{ order_line : contains
    menu_item ||--o{ order_line : "ordered as"
    orders ||--o{ order_status_history : "audit trail"
    orders ||--o{ notification : "about"
    outlet ||--o{ app_user : "staff and managers"
    app_user ||--o{ draft : "saves"

    outlet {
        int id PK
        text name UK
        int auto_confirm
        int bulk_review_threshold
    }
    menu_item {
        int id PK
        int outlet_id FK
        text name
        text category
        int default_qty_per_slot
        int price
    }
    pickup_slot {
        int id PK
        text date
        text start_time
        text end_time
    }
    slot_item_availability {
        int slot_id PK
        int item_id PK
        int capacity
        int is_unavailable
        text unavailable_reason
    }
    orders {
        int id PK
        int outlet_id FK
        int slot_id FK
        text customer_id
        text customer_name
        text status
        text pickup_code
        text review_reason
        text closure_reason
        text payment_ref
        text created_at
    }
    order_line {
        int order_id PK
        int item_id PK
        int quantity
    }
    order_status_history {
        int id PK
        int order_id FK
        text from_status
        text to_status
        text actor
        text reason
        text timestamp
    }
    notification {
        int id PK
        text recipient
        int order_id FK
        text message
        text created_at
        int is_read
    }
    app_setting {
        text key PK
        text value
    }
    app_user {
        int id PK
        text username UK
        text password_hash
        text salt
        text role
        text display_name
        text campus_id
        int outlet_id FK
    }
    draft {
        int user_id PK
        text key PK
        text value
        text updated_at
    }
```

`app_setting` holds the persisted app clock (`app_clock`) and the `schema_version`; it has no
relations. `draft.value` is JSON (a widget value keyed like `qty_<outlet>_<item>` or
`reason_<order>`). `orders.payment_ref` is a `DEMO-...` reference, or null for pay at counter.
`notification.order_id` is nullable (availability-flag alerts are not tied to one order), and
`recipient` is a plain string: `customer:<campus id>` or `outlet:<outlet id>`.

## 6. Key design decisions

| Decision | Where | Why |
| --- | --- | --- |
| Availability derived from orders, never a stored counter | `availability._ITEM_SQL` | A counter can drift; one formula serves seed and live data (BR-03, A5). |
| Stock reserved at submit, not at confirmation | `ordering.submit_order` | Two customers can never be accepted for the same last unit. |
| One transition table drives every action | `core/rules.py: TRANSITIONS` | Explainability (NFR-04); UI buttons come from `allowed_actions`. |
| One short-lived connection per operation, `isolation_level=None`, explicit `BEGIN IMMEDIATE` | `core/db.py: connect, tx` | Atomic check-and-reserve (BR-05, NFR-02); no shared connection across Streamlit sessions. |
| Confirm checks flags and slot end, never quantity | `lifecycle._check_confirmable` | Quantity was reserved at submit; re-checking would refuse the order that holds the last units (BR-10). |
| Notifications written inside the caller's transaction | `services/notifications.py` | A notification exists if and only if the change it describes committed. |
| App clock stored in the database | `services/clock.py`, `app_setting` | Demo date is in the past; the clock drives slot cut-offs and every timestamp (A3). |
| Pickup code returned once at submit, never by queries | `queries.list_orders` | Second factor on cancel and collect, kept after sign-in was added. |
| Slot suggestions are advice only | `services/suggestions.py` | Booking a suggested slot re-runs full `submit_order` validation (BR-22). |
| Drafts saved on every widget change | `ui.common.persist`, `services/drafts.py` | Cart and typed reasons survive sign-out, refresh and Streamlit dropping state of unrendered widgets. |
| Payment fields never leave the page | `ui.customer._checkout` | Demo only: format checks, then just a reference is stored (A10 relaxed). |
| Errors as one exception type | `core.rules.BusinessRuleError` | Services raise; `common.run_action` shows `message` and each failing `line` in place. |

## 7. Deployment and runtime

- Runs locally on Python 3.10+: `pip install -r src/requirements.txt`, then
  `streamlit run src/app.py` (NFR-01). No cloud services or external APIs.
- Dependencies: `streamlit>=1.37` (app), `pytest>=7.0` (tests). SQLite comes from the standard library.
- Data lives in `src/campus_food.db` and survives restarts. `init_db()` runs at the top of every
  app run: it creates missing tables and seeds only when no outlet exists; a database with an
  older `schema_version` is dropped and reseeded. **Reset demo data**
  drops everything and reloads the seed.
- Tests point `CAMPUS_FOOD_DB` at a temporary file, which `core.db.db_path()` reads per call.

### Known limitations

- All Streamlit sessions share one process and one SQLite file; fine for a single-machine prototype, not for many concurrent writers.
- Sign-in lives in the Streamlit session, so a browser refresh asks you to sign in again (drafts are kept).
- Demo accounts only; no sign-up or password change UI.
- Status changes appear on rerun or refresh, not by live push.
- Pending orders hold stock until staff act; overdue ones are highlighted, not auto-rejected (A14).
