"""Sign-in screen: every stakeholder signs in; role and outlet come from the account."""
import streamlit as st

from core.seed import DEMO_PASSWORD
from services import auth
from ui import common


def render() -> None:
    st.title("Campus Food Pre-Order")
    common.show_flash()
    _, middle, _ = st.columns([1, 2, 1])
    with middle:
        st.subheader("Sign in")
        with st.form("login"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign in", type="primary")
        if submitted:
            user = auth.authenticate(username, password)
            if user is None:
                st.error("Unknown username or wrong password.")
            else:
                st.session_state["user"] = user
                st.rerun()

        with st.expander("Demo accounts"):
            st.caption(f"Every demo account uses the password `{DEMO_PASSWORD}`.")
            st.dataframe(
                [{"Username": a["username"], "Role": a["role"], "Outlet": a["outlet"]}
                 for a in auth.list_demo_accounts()],
                hide_index=True)
