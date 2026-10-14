# AI usage log

One entry per significant prompt: the tool, what was asked, what was accepted, changed or
rejected, and why. Review rule: another team member reads every AI-generated function before merge.

## Catches already made (from reviewing the v1 requirements)

1. **Confirm re-applied the availability formula.** An order holding the last units would show
   available = 0 and be refused. Fixed in BR-10; tested by AT-17
   (`test_at17_confirm_does_not_recheck_quantity`).
2. **Check-and-reserve was not atomic.** Python `sqlite3` runs a plain SELECT outside the
   transaction by default. Fixed with `isolation_level=None` plus `BEGIN IMMEDIATE`
   (`core/db.py: tx`); tested by AT-12 (`test_at12_exactly_one_submit_wins_the_last_unit`).

## Entries

| # | Tool | Prompt | Accepted | Changed or rejected | Why |
| --- | --- | --- | --- | --- | --- |
| 1 | Claude Code | Plan from requirements v2, then build in `src/` | Three-layer layout, transition table, derived availability | Dropped the root `backend.py` counter model (`committed_qty`) | A stored counter can drift; v2 requires a derived figure |
| 2 | Claude Code | Write acceptance tests AT-01 .. AT-18 | All scenarios as pytest tests | Fixed AT-05 assertion: 8 units is under the bulk threshold, so it auto-confirms | Test expectation was wrong, not the code |
| 3 | Claude Code | Build the notifications bonus and the BR-20 tests | Same-transaction notification rows, inbox with unread badge | Customer own cancel notifies the outlet only; no customer message for it | The customer just did it, a message to them is noise |
| 4 | Claude Code | Build the next-available-slot bonus | Suggestions as advice only; booking re-runs `submit_order` | Rejected showing the live figure as a promise; test asserted Pending for 7 units | Quantity can change between suggestion and click; 7 is under the bulk threshold, so Confirmed |
