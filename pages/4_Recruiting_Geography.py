import json
import math
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import pydeck as pdk
import streamlit as st

from utils.components import colored_metric, divider, load_theme_colors
from utils.data import load_css


st.set_page_config(page_title="Recruiting & Geography", layout="wide")

# Shared visual styles.
load_css(
    "styles/base.css",
    "styles/layout.css",
    "styles/cards.css",
    "styles/player_dashboard.css",
)

st.markdown(
    """
    <style>
    .recruiting-subtitle {
        color: #6f6f6f;
        font-size: 0.95rem;
        margin-top: -6px;
        margin-bottom: 12px;
    }
    .recruiting-insight {
        border-radius: 16px;
        padding: 14px 18px;
        background: rgba(19, 41, 75, 0.06);
        border: 1px solid rgba(19, 41, 75, 0.12);
        margin-bottom: 12px;
    }
    .recruiting-insight h4 {
        margin: 0 0 6px 0;
        font-size: 1.05rem;
    }
    .recruiting-insight ul {
        margin: 0;
        padding-left: 18px;
        color: #2b2b2b;
        font-size: 0.92rem;
        line-height: 1.6;
    }
    .recruiting-panel {
        border-radius: 18px;
        padding: 14px 16px;
        background: rgba(19, 41, 75, 0.05);
        border: 1px solid rgba(19, 41, 75, 0.1);
        margin-bottom: 10px;
    }
    .recruiting-meta {
        color: #6f6f6f;
        font-size: 0.85rem;
        margin-top: -6px;
    }
    .sidebar-overview {
        border-radius: 16px;
        padding: 16px 18px;
        background: rgba(19, 41, 75, 0.06);
        border: 1px solid rgba(19, 41, 75, 0.12);
    }
    .sidebar-title {
        font-size: 0.8rem;
        color: #6f6f6f;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-weight: 700;
        margin-bottom: 6px;
    }
    .sidebar-headline {
        font-size: 1.2rem;
        font-weight: 800;
        margin: 0 0 10px 0;
    }
    .sidebar-overview h4 {
        margin: 8px 0 8px 0;
        font-size: 1.02rem;
        letter-spacing: 0.02em;
        color: #1b1b1b;
    }
    .sidebar-section-list {
        margin: 0;
        padding-left: 18px;
        color: #1f1f1f;
        font-size: 0.92rem;
        line-height: 1.6;
    }
    .sidebar-section-list li {
        margin-bottom: 6px;
    }
    .sidebar-subtext {
        font-size: 0.9rem;
        color: #2b2b2b;
        margin: 6px 0 10px 0;
        line-height: 1.5;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Theme palette.
THEME_COLORS = load_theme_colors()
PRIMARY = THEME_COLORS["primary"]
SECONDARY = THEME_COLORS["secondary"]
SUCCESS = THEME_COLORS.get("success", "#2f855a")
WARNING = THEME_COLORS.get("warning", "#c05621")
MUTED = THEME_COLORS.get("muted", "#6b6b6b")


def season_sort_key(season_label: str) -> int:
    try:
        return int(str(season_label).split("-")[0])
    except (ValueError, AttributeError, IndexError):
        return 0


STATE_MAP = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
    "district of columbia": "DC",
    "puerto rico": "PR",
}
STATE_ABBREVS = {abbr for abbr in STATE_MAP.values()}
ALT_STATE_ABBREVS = {
    "ALA": "AL",
    "ARIZ": "AZ",
    "ARK": "AR",
    "CAL": "CA",
    "CALIF": "CA",
    "COLO": "CO",
    "CONN": "CT",
    "DEL": "DE",
    "FLA": "FL",
    "GA": "GA",
    "ILL": "IL",
    "IND": "IN",
    "IOWA": "IA",
    "KANS": "KS",
    "KAN": "KS",
    "KY": "KY",
    "LA": "LA",
    "MASS": "MA",
    "MICH": "MI",
    "MINN": "MN",
    "MISS": "MS",
    "MO": "MO",
    "MONT": "MT",
    "NEB": "NE",
    "NEBR": "NE",
    "NEV": "NV",
    "N MEX": "NM",
    "NMEX": "NM",
    "N YORK": "NY",
    "N DAK": "ND",
    "S DAK": "SD",
    "OKLA": "OK",
    "ORE": "OR",
    "PENN": "PA",
    "PENNA": "PA",
    "TENN": "TN",
    "TEX": "TX",
    "UTAH": "UT",
    "VT": "VT",
    "VA": "VA",
    "WASH": "WA",
    "WISC": "WI",
    "WIS": "WI",
    "WYO": "WY",
    "DC": "DC",
    "PR": "PR",
}


def normalize_token(token: str) -> str:
    cleaned = "".join(ch for ch in token if ch.isalnum() or ch.isspace())
    return cleaned.strip()


def parse_state_and_country(hometown: str):
    if not hometown:
        return None, None
    parts = [p.strip() for p in str(hometown).split(",") if p.strip()]
    if not parts:
        return None, None
    normalized_parts = [normalize_token(part) for part in parts]
    for part in reversed(normalized_parts):
        token_upper = part.upper().replace(" ", "")
        token_spaced = part.upper()
        token_lower = part.lower()
        if token_upper in STATE_ABBREVS:
            return token_upper, "United States"
        if token_spaced in ALT_STATE_ABBREVS:
            return ALT_STATE_ABBREVS[token_spaced], "United States"
        if token_upper in ALT_STATE_ABBREVS:
            return ALT_STATE_ABBREVS[token_upper], "United States"
        if token_lower in STATE_MAP:
            return STATE_MAP[token_lower], "United States"
        if token_lower in {"ill", "illinois"}:
            return "IL", "United States"
        if token_lower in {"pr", "puerto rico"}:
            return "PR", "United States"

        # Check for tokens inside the part (e.g., "Champaign Ill")
        for word in part.split():
            word_upper = word.upper()
            word_lower = word.lower()
            if word_upper in STATE_ABBREVS:
                return word_upper, "United States"
            if word_upper in ALT_STATE_ABBREVS:
                return ALT_STATE_ABBREVS[word_upper], "United States"
            if word_lower in STATE_MAP:
                return STATE_MAP[word_lower], "United States"
            if word_lower in {"ill", "illinois"}:
                return "IL", "United States"
            if word_lower in {"pr", "puerto rico"}:
                return "PR", "United States"

    return None, normalized_parts[-1]


def latest_data_update_for(paths):
    latest_ts = None
    if isinstance(paths, (str, Path)):
        paths = [paths]
    for item in paths:
        item_path = Path(item)
        if item_path.is_dir():
            candidates = item_path.rglob("*")
        elif "*" in str(item_path):
            candidates = item_path.parent.glob(item_path.name)
        else:
            candidates = [item_path]
        for path in candidates:
            if path.is_file():
                ts = path.stat().st_mtime
                if latest_ts is None or ts > latest_ts:
                    latest_ts = ts
    if latest_ts is None:
        return "N/A"
    return datetime.fromtimestamp(latest_ts).strftime("%b %d, %Y")


def load_player_list():
    with open("data/processed/player_list.json", "r", encoding="utf-8") as f:
        return json.load(f)


def load_player_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_recruiting_df():
    player_list = load_player_list()
    rows = []
    for player_name, info in player_list.items():
        json_file = info[2] if len(info) > 2 else None
        if not json_file:
            continue
        player_path = Path("data/processed/players") / json_file
        if not player_path.exists():
            continue
        player_data = load_player_json(str(player_path))
        header = player_data.get("header", {})
        geocode = player_data.get("geocode", {}) or {}
        seasons = player_data.get("seasons") or (info[1] if len(info) > 1 else [])
        hometown = geocode.get("hometown") or header.get("Hometown")
        lat = geocode.get("lat")
        lon = geocode.get("lon")
        has_geocode = lat is not None and lon is not None

        state, country = parse_state_and_country(hometown)
        if country is None and state:
            country = "United States"
        if country is None and has_geocode:
            country = "Unknown"
        is_international = False
        if country and country != "United States":
            is_international = True
        elif state is None and has_geocode:
            is_international = True
        is_us = not is_international
        is_illinois = geocode.get("is_illinois")
        if is_illinois is None:
            is_illinois = state == "IL"

        rows.append(
            {
                "Player": player_name,
                "Hometown": hometown,
                "High School": header.get("High School"),
                "Class": header.get("Class"),
                "Position": header.get("Position"),
                "Seasons": seasons,
                "seasons_played": len(seasons) if seasons else 0,
                "lat": lat,
                "lon": lon,
                "state": state,
                "country": country,
                "is_illinois": bool(is_illinois),
                "is_us": bool(is_us),
                "is_international": bool(is_international),
                "has_geocode": bool(has_geocode),
            }
        )

    df = pd.DataFrame(rows)
    for col in [
        "Player",
        "Hometown",
        "High School",
        "Class",
        "Position",
        "Seasons",
        "seasons_played",
        "lat",
        "lon",
        "state",
        "country",
        "is_illinois",
        "is_us",
        "is_international",
        "has_geocode",
    ]:
        if col not in df.columns:
            df[col] = None
    df = df.drop_duplicates(subset=["Player"])
    try:
        df.to_csv("data/processed/recruiting_geography.csv", index=False)
    except Exception:
        pass
    return df


def load_minutes_for_season(season: str):
    path = Path("data/processed/player_stats") / f"{season}.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    if "Player" not in df.columns:
        return {}
    df["Player"] = df["Player"].astype(str).str.strip()
    for col in df.columns:
        if col != "Player":
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "Minutes AVG" in df.columns:
        minutes = df[["Player", "Minutes AVG"]].dropna()
        return dict(zip(minutes["Player"], minutes["Minutes AVG"]))
    if "Minutes TOT" in df.columns and "GP" in df.columns:
        df["Minutes AVG"] = df["Minutes TOT"] / df["GP"]
        minutes = df[["Player", "Minutes AVG"]].dropna()
        return dict(zip(minutes["Player"], minutes["Minutes AVG"]))
    return {}


def haversine_miles(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    r = 3958.8
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def geo_group(row):
    if row.get("is_international"):
        return "International"
    if row.get("is_illinois"):
        return "Illinois"
    return "US (non-IL)"


def add_distances(df: pd.DataFrame):
    if df.empty:
        return df
    df = df.copy()
    df["distance_miles"] = df.apply(
        lambda row: haversine_miles(40.1164, -88.2434, row["lat"], row["lon"]),
        axis=1,
    )
    return df


st.title("Recruiting & Geography")
st.markdown(
    "<div class='recruiting-subtitle'>Where Illini talent comes from, and how the pipeline evolves.</div>",
    unsafe_allow_html=True,
)

data_updated = latest_data_update_for(
    ["data/processed/player_list.json", "data/processed/players"]
)
st.markdown(
    f"<div class='recruiting-meta'>Last updated: {data_updated}</div>",
    unsafe_allow_html=True,
)

divider(PRIMARY)

df_season_stats = pd.read_csv("data/processed/season_stats.csv")
df_illinois_stats = df_season_stats[df_season_stats["Team"] == "Illinois"].copy()
season_options = sorted(df_illinois_stats["Season"].dropna().unique().tolist(), key=season_sort_key)
latest_season = season_options[-1] if season_options else None

base_df = build_recruiting_df()
if base_df.empty:
    st.info("No recruiting geography data is available yet.")
    st.stop()
if base_df["Player"].duplicated().any():
    st.warning("Duplicate player records were detected in the recruiting dataset.")

# Normalize class/position to keep missing values selectable.
base_df = base_df.copy()
base_df["Class"] = base_df["Class"].fillna("Unknown").astype(str).str.strip()
base_df["Position"] = base_df["Position"].fillna("Unknown").astype(str).str.strip()
base_df["Class"] = base_df["Class"].replace(
    {"": "Unknown", "None": "Unknown", "nan": "Unknown"}
)
base_df["Position"] = base_df["Position"].replace(
    {"": "Unknown", "None": "Unknown", "nan": "Unknown"}
)

with st.sidebar:
    st.markdown(
        f"""
        <div class="sidebar-overview">
            <div class="sidebar-title">Recruiting & Geography</div>
            <div class="sidebar-headline" style="color:{PRIMARY};">Pipeline Snapshot</div>
            <div class="sidebar-subtext">
                Explore where Illini talent comes from and how the recruiting footprint evolves.
            </div>
            <h4>What you'll find</h4>
            <ul class="sidebar-section-list">
                <li>Roster source map with clustering + minutes scaling</li>
                <li>State and country pipeline breakdowns</li>
                <li>Distance-from-Champaign context</li>
                <li>Season-by-season pipeline shifts</li>
                <li>Missing geocode audit list</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

controls_left, controls_right = st.columns([1.2, 2.8])
with controls_left:
    st.markdown("<div class='recruiting-panel'>", unsafe_allow_html=True)
    display_mode = st.radio(
        "Display mode",
        ["Current Roster", "All Seasons", "By Season"],
        horizontal=False,
        key="rg_display_mode",
    )
    selected_season = None
    if display_mode == "By Season":
        if season_options:
            selected_season = st.selectbox(
                "Select a season",
                options=season_options[::-1],
                index=0,
                key="rg_season_select",
            )
        else:
            st.caption("No seasons available for selection.")
    geo_options = ["Illinois", "US (non-IL)", "International"]
    geo_filter = st.multiselect(
        "Geography",
        options=geo_options,
        default=geo_options,
        key="rg_geo_filter",
    )

    class_options = (
        base_df["Class"].astype(str).unique().tolist()
        if "Class" in base_df.columns
        else []
    )
    class_options = sorted(class_options, key=lambda x: x)
    class_filter = st.multiselect(
        "Class",
        options=class_options,
        default=class_options,
        key="rg_class_filter",
    )

    position_options = (
        base_df["Position"].astype(str).unique().tolist()
        if "Position" in base_df.columns
        else []
    )
    position_options = sorted(position_options, key=lambda x: x)
    position_filter = st.multiselect(
        "Position",
        options=position_options,
        default=position_options,
        key="rg_position_filter",
    )

    cluster_points = st.toggle("Cluster nearby points", value=False, key="rg_cluster_points")
    scale_by_minutes = st.toggle("Scale marker by minutes", value=False, key="rg_scale_minutes")

    if st.button("Reset filters", width="stretch"):
        st.session_state["rg_display_mode"] = "Current Roster"
        st.session_state["rg_season_select"] = season_options[::-1][0] if season_options else None
        st.session_state["rg_geo_filter"] = geo_options
        st.session_state["rg_class_filter"] = class_options
        st.session_state["rg_position_filter"] = position_options
        st.session_state["rg_cluster_points"] = False
        st.session_state["rg_scale_minutes"] = False
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

filtered_df = base_df.copy()
if display_mode == "Current Roster" and latest_season:
    filtered_df = filtered_df[
        filtered_df["Seasons"].apply(lambda seasons: latest_season in (seasons or []))
    ]
elif display_mode == "By Season" and selected_season:
    filtered_df = filtered_df[
        filtered_df["Seasons"].apply(lambda seasons: selected_season in (seasons or []))
    ]

filtered_df = filtered_df.copy()
filtered_df["geo_group"] = filtered_df.apply(geo_group, axis=1)

def sanitize_filter(selected, options):
    if not selected:
        return []
    return [item for item in selected if item in options]

geo_filter = sanitize_filter(geo_filter, geo_options)
class_filter = sanitize_filter(class_filter, class_options)
position_filter = sanitize_filter(position_filter, position_options)

if geo_filter:
    filtered_df = filtered_df[filtered_df["geo_group"].isin(geo_filter)]
if class_filter:
    filtered_df = filtered_df[filtered_df["Class"].isin(class_filter)]
if position_filter:
    filtered_df = filtered_df[filtered_df["Position"].isin(position_filter)]

filtered_df = filtered_df.reset_index(drop=True)
map_df = filtered_df[filtered_df["has_geocode"]].copy()
missing_df = filtered_df[~filtered_df["has_geocode"]].copy()

if scale_by_minutes and (display_mode == "By Season" and selected_season):
    minutes_map = load_minutes_for_season(selected_season)
elif scale_by_minutes and display_mode == "Current Roster" and latest_season:
    minutes_map = load_minutes_for_season(latest_season)
else:
    minutes_map = {}

if minutes_map and scale_by_minutes:
    map_df["minutes_avg"] = map_df["Player"].map(minutes_map)
else:
    map_df["minutes_avg"] = None

if not map_df.empty:
    map_df["seasons_label"] = map_df["Seasons"].apply(lambda s: ", ".join(s) if s else "N/A")
    map_df["category_label"] = map_df["geo_group"]
    map_df["tooltip_high_school"] = map_df["High School"].fillna("N/A")
    map_df["tooltip_class"] = map_df["Class"].fillna("N/A")
else:
    map_df["seasons_label"] = []

with controls_right:
    total_players = len(filtered_df)
    illinois_count = int(filtered_df["is_illinois"].sum()) if total_players else 0
    international_count = int(filtered_df["is_international"].sum()) if total_players else 0
    us_non_il_count = total_players - illinois_count - international_count

    def pct(value):
        if total_players == 0:
            return "0%"
        return f"{value / total_players:.0%}"

    metric_items = [
        ("Players", f"{total_players}", "Filtered roster size"),
        ("Illinois", f"{illinois_count}", f"{pct(illinois_count)} of roster"),
        ("US (non-IL)", f"{us_non_il_count}", f"{pct(us_non_il_count)} of roster"),
        ("International", f"{international_count}", f"{pct(international_count)} of roster"),
        (
            "States Represented",
            f"{filtered_df['state'].dropna().nunique()}",
            "Unique states in view",
        ),
        (
            "Countries Represented",
            f"{filtered_df['country'].dropna().nunique()}",
            "Unique countries in view",
        ),
    ]
    metric_cols = st.columns(3)
    for idx, (label, value, delta) in enumerate(metric_items):
        card = colored_metric(
            label=label,
            value=value,
            val_color=PRIMARY,
            bg_color="white",
            border_color="#13294B",
            delta=delta,
            delta_b_color=SECONDARY,
            delta_t_color="#FFFFFF",
        )
        with metric_cols[idx % 3]:
            st.markdown(card, unsafe_allow_html=True)

divider(PRIMARY)

insight_lines = []
if total_players:
    insight_lines.append(
        f"Roster spans {filtered_df['state'].dropna().nunique()} states and {filtered_df['country'].dropna().nunique()} countries."
    )
    insight_lines.append(f"Illinois accounts for {pct(illinois_count)} of the filtered roster.")
    if international_count:
        insight_lines.append(f"{international_count} international players appear in this view.")

if insight_lines:
    st.markdown(
        f"""
        <div class="recruiting-insight">
            <h4>Storyline</h4>
            <ul>
                {''.join(f"<li>{line}</li>" for line in insight_lines[:3])}
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

map_section_left, map_section_right = st.columns([3.3, 1.1])
with map_section_right:
    st.markdown("**Jump to a player**")
    player_options = map_df["Player"].tolist() if not map_df.empty else []
    player_select = st.selectbox(
        "View Player",
        options=["Select..."] + player_options,
        label_visibility="collapsed",
    )
    if player_select and player_select != "Select...":
        if st.button("Open Player Dashboard", width="stretch"):
            st.session_state["selected_player"] = player_select
            st.switch_page("pages/3_Player_Dashboards.py")

with map_section_left:
    if map_df.empty:
        st.info("No players match the current filters with valid geocodes.")
    else:
        map_center_lat = map_df["lat"].mean()
        map_center_lon = map_df["lon"].mean()
        if map_df["is_international"].any():
            zoom = 1.6
        elif map_df["is_illinois"].all():
            zoom = 6.2
            map_center_lat = 40.05
            map_center_lon = -89.25
        else:
            zoom = 3.2
            map_center_lat = 39.5
            map_center_lon = -98.35

        view_state = pdk.ViewState(
            latitude=float(map_center_lat),
            longitude=float(map_center_lon),
            zoom=zoom,
            pitch=35,
        )

        color_map = {
            "Illinois": [19, 41, 75, 200],
            "US (non-IL)": [255, 95, 5, 190],
            "International": [42, 157, 143, 190],
        }

        if cluster_points:
            layer = pdk.Layer(
                "HexagonLayer",
                data=map_df,
                get_position="[lon, lat]",
                radius=85000,
                elevation_scale=20,
                elevation_range=[0, 1000],
                pickable=True,
                extruded=False,
            )
            tooltip = {"html": "<b>Players:</b> {count}", "style": {"background": "#1b1b1b", "color": "white"}}
        else:
            radius_field = None
            if scale_by_minutes and map_df["minutes_avg"].notna().any():
                map_df["radius_val"] = map_df["minutes_avg"].fillna(map_df["minutes_avg"].median())
                radius_field = "radius_val"
            elif map_df["seasons_played"].notna().any():
                map_df["radius_val"] = map_df["seasons_played"].fillna(1)
                radius_field = "radius_val"
            map_df["color"] = map_df["geo_group"].map(color_map)
            layer = pdk.Layer(
                "ScatterplotLayer",
                data=map_df,
                get_position="[lon, lat]",
                get_fill_color="color",
                get_radius=radius_field or 60000,
                radius_scale=4000 if radius_field else 1,
                radius_min_pixels=6,
                radius_max_pixels=20,
                pickable=True,
            )
            tooltip = {
                "html": """
                <div style='font-size:0.85rem;'>
                    <b>{Player}</b><br/>
                    {Hometown}<br/>
                    High School: {tooltip_high_school}<br/>
                    Class: {tooltip_class}<br/>
                    Seasons: {seasons_label}<br/>
                    Category: {category_label}
                </div>
                """,
                "style": {"background": "#f7f7f7", "color": "#111111"},
            }

        deck = pdk.Deck(
            layers=[layer],
            initial_view_state=view_state,
            map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
            tooltip=tooltip,
        )
        st.pydeck_chart(deck, width="stretch", height=540)

divider(PRIMARY)

if map_df.empty:
    st.info("No geocoded players available for the current filters.")
else:
    map_df = add_distances(map_df)

    left_chart, right_chart = st.columns(2)

    with left_chart:
        state_counts = (
            map_df.dropna(subset=["state"])
            .groupby("state")
            .size()
            .reset_index(name="Players")
            .sort_values("Players", ascending=False)
            .head(10)
        )
        if state_counts.empty:
            st.info("No state data available for the current filters.")
        else:
            fig_states = px.bar(
                state_counts,
                x="state",
                y="Players",
                title="Top States (Players)",
                color_discrete_sequence=[PRIMARY],
            )
            fig_states.update_traces(marker_line_width=0, hovertemplate=None)
            fig_states.update_layout(
                showlegend=False,
                hoverlabel=dict(
                    bgcolor="#f4f4f4",
                    bordercolor=SECONDARY,
                    font=dict(color=SECONDARY, size=12),
                ),
            )
            st.plotly_chart(fig_states, width="stretch")

    with right_chart:
        intl_df = map_df[map_df["is_international"]]
        country_counts = (
            intl_df.dropna(subset=["country"])
            .groupby("country")
            .size()
            .reset_index(name="Players")
            .sort_values("Players", ascending=False)
            .head(10)
        )
        if country_counts.empty:
            st.info("No international country counts for the current filters.")
        else:
            fig_countries = px.bar(
                country_counts,
                x="country",
                y="Players",
                title="Top Countries (International Players)",
                color_discrete_sequence=[PRIMARY],
            )
            fig_countries.update_traces(marker_line_width=0, hovertemplate=None)
            fig_countries.update_layout(
                showlegend=False,
                hoverlabel=dict(
                    bgcolor="#f4f4f4",
                    bordercolor=SECONDARY,
                    font=dict(color=SECONDARY, size=12),
                ),
            )
            st.plotly_chart(fig_countries, width="stretch")

    divider(PRIMARY)

    distance_values = map_df["distance_miles"].dropna()
    if not distance_values.empty:
        avg_distance = distance_values.mean()
        median_distance = distance_values.median()
        farthest_idx = map_df["distance_miles"].idxmax()
        farthest_player = map_df.loc[farthest_idx, "Player"] if pd.notna(farthest_idx) else "N/A"
        if not farthest_player:
            farthest_player = "N/A"
        dist_cols = st.columns(3)
        dist_cards = [
            ("Avg Distance (mi)", f"{avg_distance:.0f}", "From Champaign"),
            ("Median Distance (mi)", f"{median_distance:.0f}", "From Champaign"),
            ("Farthest Recruit (mi)", f"{distance_values.max():.0f}", farthest_player),
        ]
        for idx, (label, value, delta) in enumerate(dist_cards):
            card = colored_metric(
                label=label,
                value=value,
                val_color=PRIMARY,
                bg_color="white",
                border_color="#13294B",
                delta=delta,
                delta_b_color=SECONDARY,
                delta_t_color="#FFFFFF",
            )
            with dist_cols[idx % 3]:
                st.markdown(card, unsafe_allow_html=True)

        fig_dist = px.histogram(
            distance_values,
            nbins=12,
            title="Distance to Champaign (Miles)",
        )
        fig_dist.update_traces(marker_color=SECONDARY, hovertemplate=None)
        fig_dist.update_layout(
            showlegend=False,
            hoverlabel=dict(
                bgcolor="#f4f4f4",
                bordercolor=SECONDARY,
                font=dict(color=SECONDARY, size=12),
            ),
        )
        st.plotly_chart(fig_dist, width="stretch")

    pipeline_states = (
        map_df.dropna(subset=["state"])
        .groupby("state")
        .size()
        .reset_index(name="Players")
    )
    pipeline_states = pipeline_states[pipeline_states["Players"] >= 2].sort_values(
        "Players", ascending=False
    )
    pipeline_countries = (
        map_df[map_df["is_international"]]
        .dropna(subset=["country"])
        .groupby("country")
        .size()
        .reset_index(name="Players")
    )
    pipeline_countries = pipeline_countries[
        pipeline_countries["Players"] >= 2
    ].sort_values("Players", ascending=False)

    pipeline_left, pipeline_right = st.columns(2)
    with pipeline_left:
        st.subheader("Top State Pipelines")
        if pipeline_states.empty:
            st.caption("No states with 2+ players in the current view.")
        else:
            st.dataframe(pipeline_states, width="stretch", hide_index=True)
    with pipeline_right:
        st.subheader("Top Country Pipelines")
        if pipeline_countries.empty:
            st.caption("No countries with 2+ players in the current view.")
        else:
            st.dataframe(pipeline_countries, width="stretch", hide_index=True)

    if display_mode == "By Season" and selected_season:
        prior_df = base_df[
            base_df["Seasons"].apply(
                lambda seasons: any(season_sort_key(s) < season_sort_key(selected_season) for s in (seasons or []))
            )
        ]
        new_states = set(map_df["state"].dropna()) - set(prior_df["state"].dropna())
        new_countries = set(map_df["country"].dropna()) - set(prior_df["country"].dropna())
        if new_states or new_countries:
            st.subheader("New Pipelines This Season")
            cols = st.columns(2)
            with cols[0]:
                st.markdown("**New States**")
                if new_states:
                    st.markdown(", ".join(sorted(new_states)))
                else:
                    st.caption("No new states this season.")
            with cols[1]:
                st.markdown("**New Countries**")
                if new_countries:
                    st.markdown(", ".join(sorted(new_countries)))
                else:
                    st.caption("No new countries this season.")

divider(PRIMARY)

if not missing_df.empty:
    with st.expander("Missing Geocode Data"):
        st.caption("These players are excluded from map-based stats.")
        st.dataframe(
            missing_df[["Player", "Hometown", "High School"]].fillna("N/A"),
            width="stretch",
            hide_index=True,
        )

invalid_geo = map_df[
    (map_df["lat"].notna() & ((map_df["lat"] < -90) | (map_df["lat"] > 90)))
    | (map_df["lon"].notna() & ((map_df["lon"] < -180) | (map_df["lon"] > 180)))
]
if not invalid_geo.empty:
    st.warning("Some geocode values fall outside valid latitude/longitude ranges.")

flag_mismatch = map_df[
    (map_df["is_international"] & map_df["is_us"])
    | (~map_df["is_international"] & ~map_df["is_us"])
]
if not flag_mismatch.empty:
    st.warning("Some rows have inconsistent geographic flags (international vs US).")

st.subheader("Explore More Pages!")
st.markdown(
    """
    There are multiple ways to dive into the statistics behind the **Illini Men's Basketball Team**.
    Use the buttons below to travel to the corresponding page!
    """
)
nan1, left, mid, right, nan2 = st.columns([0.25, 2, 2, 2, 0.25])
with left:
    if st.button("Home", width="stretch"):
        st.switch_page("Home.py")
    st.markdown(
        """
        <p style="text-align:center; font-size:0.9rem; color:#6b6b6b;">
            Return to the dashboard landing page.
        </p>
        """,
        unsafe_allow_html=True,
    )
with mid:
    if st.button("Team Overviews", width="stretch"):
        st.switch_page("pages/2_Team_Overviews.py")
    st.markdown(
        """
        <p style="text-align:center; font-size:0.9rem; color:#6b6b6b;">
            Explore the statistics surrounding a specific season.
        </p>
        """,
        unsafe_allow_html=True,
    )
with right:
    if st.button("Player Dashboards", width="stretch"):
        st.switch_page("pages/3_Player_Dashboards.py")
    st.markdown(
        """
        <p style="text-align:center; font-size:0.9rem; color:#6b6b6b;">
            Explore the information and statistics on each player who's ever been on the Illinois roster.
        </p>
        """,
        unsafe_allow_html=True,
    )
