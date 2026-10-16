"""Returns Tracker — Streamlit entry point. Run with: streamlit run app.py"""
import streamlit as st

from tracker import db
from tracker.seed import seed

st.set_page_config(page_title="Returns Tracker", page_icon="📱", layout="wide")


@st.cache_resource
def get_connection():
    conn = db.connect()
    db.init_db(conn)
    if db.is_empty(conn):  # free hosting resets storage on restart, so reload the demo data
        seed(conn)
    return conn


st.session_state.conn = get_connection()

pages = st.navigation([
    st.Page("pages/log_return.py", title="Log a return", icon="📝"),
    st.Page("pages/returns_log.py", title="Returns log", icon="📋"),
    st.Page("pages/dashboard.py", title="Manager dashboard", icon="📊", default=True),
])
pages.run()
