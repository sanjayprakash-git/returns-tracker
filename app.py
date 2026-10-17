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
        st.caption("Faulty stock, supplier returns and repair comebacks for a phone repair & electronics shop.")
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
            st.caption("Staff use Counter, Faulty box and Stock; the manager also sees Money. "
                       "Demo data, staff and supplier names are fictional.")


user = st.session_state.get("user")
if not user:
    st.navigation([st.Page(sign_in, title="Sign in", icon="🔐")]).run()
    st.stop()

with st.sidebar:
    st.markdown(f"Signed in as **{user['name']}**  \n{user['role'].capitalize()}")
    if st.button("Sign out"):
        del st.session_state.user
        st.rerun()

is_manager = user["role"] == "manager"
pages = [
    st.Page("views/counter.py", title="Counter", icon="🔁", default=not is_manager),
    st.Page("views/faulty_box.py", title="Faulty box", icon="♻️"),
    st.Page("views/stock_view.py", title="Stock", icon="📦"),
]
if is_manager:
    pages.insert(0, st.Page("views/money.py", title="Money", icon="💶", default=True))
st.navigation(pages).run()
