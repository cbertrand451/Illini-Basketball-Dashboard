import json
from pathlib import Path

import streamlit as st

from utils.components import divider, load_theme_colors, pill_button_styler
from utils.data import load_css

st.set_page_config(page_title="Media Showcase", layout="wide")

load_css(
    "styles/base.css",
    "styles/layout.css",
    "styles/cards.css",
    "styles/player_dashboard.css",
)

THEME_COLORS = load_theme_colors()
PRIMARY = THEME_COLORS["primary"]
SECONDARY = THEME_COLORS["secondary"]

st.markdown(
    """
    <style>
    .media-hero {
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
        gap: 10px;
        margin-top: 6px;
        margin-bottom: 10px;
    }
    .media-hero h1 {
        font-family: "Space Grotesk", "Montserrat", "Helvetica Neue", Arial, sans-serif;
        font-weight: 700;
        font-size: clamp(26px, 2.6vw, 40px);
        margin: 0;
    }
    .media-hero p {
        max-width: 700px;
        color: #4b4b4b;
        font-size: 1rem;
        margin: 0;
    }
    .media-chip-row {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
        justify-content: center;
    }
    .media-chip {
        padding: 6px 12px;
        border-radius: 999px;
        background: rgba(19, 41, 75, 0.08);
        color: #13294b;
        font-weight: 600;
        font-size: 0.85rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <section class="media-hero">
        <h1 style="color:{PRIMARY};">Media Showcase</h1>
        <p>Every action photo available across the Illini Men's Basketball dataset.</p>
    </section>
    """,
    unsafe_allow_html=True,
)

divider(SECONDARY)

player_list_path = Path("data/processed/player_list.json")
player_list = {}
if player_list_path.exists():
    with player_list_path.open("r", encoding="utf-8") as f:
        player_list = json.load(f)

photos = []
photos_by_url = {}
players_with_photos = set()

def register_photo(url, player_name=None, credit=None):
    if not url:
        return
    existing = photos_by_url.get(url)
    if existing:
        if not existing.get("credit") and credit:
            existing["credit"] = credit
        if not existing.get("player") and player_name:
            existing["player"] = player_name
        return
    record = {
        "url": url,
        "player": player_name or "Illinois MBB",
        "credit": credit or "",
    }
    photos_by_url[url] = record
    photos.append(record)


players_dir = Path("data/processed/players")
for player_name, info in player_list.items():
    if len(info) < 3:
        continue
    json_file = info[2]
    player_path = players_dir / json_file
    if not player_path.exists():
        continue
    try:
        with player_path.open("r", encoding="utf-8") as f:
            player_data = json.load(f)
    except Exception:
        continue
    action_photos = player_data.get("action photos", []) or []
    if action_photos:
        players_with_photos.add(player_name)
    for photo in action_photos:
        if isinstance(photo, dict):
            url = photo.get("url")
            credit = photo.get("credit")
        else:
            url = photo
            credit = None
        register_photo(url, player_name=player_name, credit=credit)


action_list_path = Path("data/images/action_photos.json")
if action_list_path.exists():
    try:
        with action_list_path.open("r", encoding="utf-8") as f:
            action_urls = json.load(f) or []
        for url in action_urls:
            register_photo(url)
    except Exception:
        action_urls = []

photos = sorted(photos, key=lambda item: (item.get("player") or "", item.get("url") or ""))

pill_button_styler(primary=PRIMARY, secondary=SECONDARY, font_size="0.9rem", padding_y="6px")
if "media_cols" not in st.session_state:
    st.session_state["media_cols"] = 4

st.markdown("<div style='text-align:center; color:#6f6f6f; font-size:0.9rem;'>Photo size</div>", unsafe_allow_html=True)
pill_left, pill_mid, pill_right = st.columns(3)
with pill_left:
    if st.button("Normal (4 per row)", width="stretch"):
        st.session_state["media_cols"] = 4
with pill_mid:
    if st.button("Large (2 per row)", width="stretch"):
        st.session_state["media_cols"] = 2
with pill_right:
    if st.button("X-Large (1 per row)", width="stretch"):
        st.session_state["media_cols"] = 1

num_cols = st.session_state["media_cols"]

st.markdown(
    f"""
    <div class="media-chip-row">
        <div class="media-chip">Total photos: {len(photos)}</div>
        <div class="media-chip">Players with photos: {len(players_with_photos)}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

divider(SECONDARY)

if not photos:
    st.info("No action photos are available right now.")
else:
    cols = st.columns(num_cols)
    for idx, entry in enumerate(photos):
        col = cols[idx % num_cols]
        caption_bits = [entry.get("player") or "Illinois MBB"]
        if entry.get("credit"):
            caption_bits.append(entry["credit"])
        caption = " • ".join(caption_bits)
        with col:
            st.image(entry["url"], caption=caption, use_container_width=True)
