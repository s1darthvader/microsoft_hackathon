"""Campus Food Pre-Order and Pickup. Run with: streamlit run src/app.py"""
import streamlit as st

from core.seed import init_db
from ui import admin, common, customer, manager, staff

PAGES = {
    "Customer": customer,
    "Outlet Staff": staff,
    "Outlet Manager": manager,
    "Campus Admin": admin,
}

st.set_page_config(page_title="Campus Food Pre-Order", page_icon="🍽️", layout="wide")
init_db()

role, ctx = common.sidebar(list(PAGES))
st.title(role)
common.show_flash()
PAGES[role].render(ctx)
