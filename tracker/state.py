"""Shared database connection for all pages (created once per server, seeded on first start)."""
import streamlit as st

from tracker import db
from tracker.seed import seed


@st.cache_resource
def get_connection():
    conn = db.connect()
    db.init_db(conn)
    if db.is_empty(conn):  # free hosting resets storage on restart, so reload the demo data
        seed(conn)
    return conn
