import streamlit as st

st.set_page_config(page_title="Illini MBB Dashboard — Landing", layout="centered")

st.title("Illini Men's Basketball Dashboard")
st.markdown("A lightweight landing page for link previews and quick summaries.")

st.markdown(
    """
    **What this site is**
    - An interactive data dashboard for Illinois Men's Basketball history
    - Built in Streamlit and maintained by Colin Bertrand

    **What it contains**
    - Team season overviews and trends
    - Player dashboards and career stats
    - Recruiting geography and program history highlights

    **Why this page exists**
    - A minimal, fast-loading page for bots and social previews
    - The full experience is available in the other dashboard pages
    """
)

st.caption("If you are viewing this as a preview bot, please index this page.")
