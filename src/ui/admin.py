"""Campus admin view: cross-outlet policy and demand (FR-A1, read only)."""
import streamlit as st

from services import availability, clock, queries


def render(ctx: dict) -> None:
    st.subheader("Outlets")
    st.dataframe(
        [{"Outlet": o["name"], "Auto-confirm": "On" if o["auto_confirm"] else "Off",
          "Bulk threshold": o["bulk_review_threshold"]} for o in queries.list_outlets()],
        hide_index=True)

    st.subheader("Demand by outlet and slot")
    date = st.selectbox("Date", queries.list_dates(), format_func=clock.long_date)
    rows = availability.slot_demand(date=date)
    st.dataframe(
        [{"Outlet": r["outlet"], "Slot": r["slot"], "Item": r["item"], "Capacity": r["capacity"],
          "Counted": r["counted"], "Available": r["available"],
          "State": r["state"].replace("_", " ")} for r in rows],
        hide_index=True)
