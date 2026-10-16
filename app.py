"""Returns Tracker — Streamlit entry point. Run with: streamlit run app.py"""
import streamlit as st

from tracker.auth import DEMO_LOGINS, DEMO_MODE, authenticate, demo_user
from tracker.state import get_connection

st.set_page_config(page_title="Returns Tracker", page_icon="📱", layout="wide")
conn = get_connection()  # create and seed the database on first start


def sign_in():
    _, middle, _ = st.columns([1, 1.2, 1])
    with middle:
        st.title("📱 Returns Tracker")
        st.caption("Repair comebacks, product returns and supplier claims for a phone repair & accessories shop.")
        with st.form("sign-in"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Sign in", type="primary", width="stretch"):
                user = authenticate(conn, username, password)
                if user:
                    st.session_state.user = user
                    st.rerun()
                st.error("Wrong username or password.")
        if DEMO_MODE:
            st.markdown("**Or try the demo**")
            cols = st.columns(len(DEMO_LOGINS))
            for col, (username, _, role) in zip(cols, DEMO_LOGINS):
                if col.button(f"Try as {role}", width="stretch", key=f"demo-{username}"):
                    st.session_state.user = demo_user(conn, username)
                    st.rerun()
            st.caption("The manager sees everything, including the dashboard. Technicians and sales staff log "
                       "returns and manage supplier claims. Demo data and supplier names are fictional.")


user = st.session_state.get("user")
if not user:
    st.navigation([st.Page(sign_in, title="Sign in", icon="🔐")]).run()
    st.stop()

with st.sidebar:
    st.markdown(f"Signed in as **{user['name']}**  \n{user['role'].capitalize()}")
    if st.button("Sign out"):
        del st.session_state.user
        st.rerun()

pages = [
    st.Page("views/log_return.py", title="Log a return", icon="📝", default=user["role"] != "manager"),
    st.Page("views/returns_log.py", title="Returns log", icon="📋"),
    st.Page("views/supplier_claims.py", title="Supplier claims", icon="📦"),
]
if user["role"] == "manager":
    pages.append(st.Page("views/dashboard.py", title="Manager dashboard", icon="📊", default=True))
st.navigation(pages).run()
