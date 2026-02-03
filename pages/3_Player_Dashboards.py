import streamlit as st
import pandas as pd
from pathlib import Path
import json
import plotly.express as px
import pydeck as pdk
import textwrap
from utils.components import colored_metric, divider, load_theme_colors, tab_styler
from utils.data import history_csvs, load_css, image_to_data_uri
from utils.player_dashboard import (
    arc_path,
    build_comparison_df,
    format_stat_value,
    normalized_value,
)

st.set_page_config(page_title="Player Dashboards", 
                   layout="wide")

# Load shared visual styles for the dashboard layout and cards.
load_css("styles/player_image.css")
load_css("styles/player_dashboard.css")
load_css("styles/cards.css")

# Inline style tweaks for the upgraded page elements (kept minimal and theme-aligned).
st.markdown(
    """
    <style>
    .role-summary-card {
        border: 1px solid rgba(19, 41, 75, 0.18);
        border-radius: 12px;
        padding: 12px 16px;
        background: #fffaf6;
        margin-top: 6px;
        margin-bottom: 12px;
    }
    .role-summary-title {
        font-size: 0.95rem;
        font-weight: 700;
        color: #13294B;
        margin-bottom: 4px;
    }
    .role-summary-text {
        font-size: 0.9rem;
        color: #2b2b2b;
        margin-bottom: 8px;
    }
    .role-summary-badges {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
    }
    .role-summary-badge {
        font-size: 0.78rem;
        padding: 4px 8px;
        border-radius: 999px;
        background: rgba(255, 95, 5, 0.12);
        color: #4b2a1d;
        border: 1px solid rgba(255, 95, 5, 0.25);
    }
    .impact-detail-card {
        margin-bottom: 16px;
    }
    .impact-detail-header {
        font-size: 0.95rem;
    }
    .impact-stat-label,
    .impact-stat-value {
        font-size: 0.92rem;
    }
    .impact-stat-delta {
        font-size: 0.78rem;
        margin-left: 6px;
    }
    .impact-stat-delta.positive {
        color: #1f7a3f;
    }
    .impact-stat-delta.negative {
        color: #a02b2b;
    }
    .impact-stat-delta.neutral {
        color: #6f6f6f;
    }
    .stat-group-label {
        font-size: 0.82rem;
        font-weight: 700;
        color: #6a6a6a;
        letter-spacing: 0.02em;
        text-transform: uppercase;
        margin-top: 10px;
        margin-bottom: 6px;
    }
    .trajectory-card {
        border: 1px solid rgba(19, 41, 75, 0.15);
        border-radius: 12px;
        padding: 14px 16px;
        background: #f8f9fb;
        margin-top: 10px;
        margin-bottom: 10px;
    }
    .trajectory-title {
        font-size: 0.95rem;
        font-weight: 700;
        color: #13294B;
        margin-bottom: 6px;
    }
    .trajectory-list {
        margin: 0;
        padding-left: 18px;
        color: #2b2b2b;
        font-size: 0.9rem;
    }
    .sidebar-overview {
        border-radius: 16px;
        padding: 16px 18px;
        background: rgba(19, 41, 75, 0.06);
        border: 1px solid rgba(19, 41, 75, 0.12);
        margin-bottom: 16px;
    }
    .sidebar-player-label {
        font-size: 0.78rem;
        color: #6f6f6f;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 4px;
        font-weight: 700;
    }
    .sidebar-player-name {
        font-size: 1.25rem;
        font-weight: 800;
        margin: 0 0 12px 0;
    }
    .sidebar-overview h4 {
        margin: 0 0 10px 0;
        font-size: 1.05rem;
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
    </style>
    """,
    unsafe_allow_html=True,
)


# Theme palette used across all components.
THEME_COLORS = load_theme_colors()
PRIMARY = THEME_COLORS['primary']
SECONDARY = THEME_COLORS['secondary']
SUCCESS = THEME_COLORS['success']
WARNING = THEME_COLORS['warning']
MUTED = THEME_COLORS['muted']

# Base team data and player index.
df_season_stats = pd.read_csv("data/processed/season_stats.csv")
df_illinois_stats = df_season_stats[df_season_stats['Team'] == "Illinois"]
seasons = df_illinois_stats['Season'].tolist()
players = []
with open("data/processed/player_list.json", "r") as f:
    data = json.load(f)
    for key in data:
        players.append(key)

# Page header and player selector.
st.title("Player Dashboards")
c_box, nan = st.columns([1.45, 4])
with c_box:
    player_options = players[::-1]
    selected_player = st.session_state.get("selected_player")
    if selected_player in player_options:
        default_index = player_options.index(selected_player)
    else:
        default_index = 0
    player = st.selectbox(
        label="Select a Player",
        options=player_options,
        index=default_index,
        key="player_select",
    )
player_json = data[player]
json_file_path = player_json[2]
with open(f"data/processed/players/{json_file_path}", "r") as f:
    player_data = json.load(f)
player_header = player_data['header']
player_seasons = player_data.get("seasons", [])


# Sort helper for "YYYY-YY" season strings.
def season_sort_key(season_label: str) -> int:
    try:
        return int(season_label.split("-")[0])
    except (ValueError, AttributeError):
        return 0


# Division helper that avoids zero/None crashes.
def safe_divide(numerator, denominator):
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


# Lightweight usage proxy based on possession-ending events per game.
def compute_usage_proxy(row):
    gp = row.get("GP")
    if not gp:
        return None
    fga = row.get("FGA") or 0
    fta = row.get("FTA") or 0
    turnovers = row.get("TO") or 0
    usage_events = fga + 0.44 * fta + turnovers
    return usage_events / gp if gp else None


# Defensive activity proxy per game.
def compute_defense_proxy(row):
    gp = row.get("GP")
    if not gp:
        return None
    steals = row.get("STL") or 0
    blocks = row.get("BLK") or 0
    defensive_rebounds = row.get("DEF") or 0
    return (steals + blocks + defensive_rebounds) / gp if gp else None


# Minutes per game with fallback from total minutes.
def compute_minutes_per_game(row):
    minutes_avg = row.get("Minutes AVG")
    if minutes_avg:
        return minutes_avg
    minutes_total = row.get("Minutes TOT")
    gp = row.get("GP")
    return safe_divide(minutes_total, gp)


# Rule-based role label and sentence summary (no model calls).
def role_label_and_summary(row):
    minutes_per_game = compute_minutes_per_game(row)
    usage_proxy = compute_usage_proxy(row)
    defense_proxy = compute_defense_proxy(row)
    assists_per_game = safe_divide(row.get("AST"), row.get("GP"))
    points_per_game = row.get("Scoring AVG") or safe_divide(row.get("PTS"), row.get("GP"))

    minutes_per_game = minutes_per_game or 0
    usage_proxy = usage_proxy or 0
    defense_proxy = defense_proxy or 0
    assists_per_game = assists_per_game or 0
    points_per_game = points_per_game or 0

    if minutes_per_game >= 28 and usage_proxy >= 12:
        label = "Primary Scorer"
        summary = "Carries the scoring workload while handling a large share of offensive possessions."
    elif minutes_per_game >= 28 and defense_proxy >= 3:
        label = "Defensive Anchor"
        summary = "Sets the tone with reliable defense and steady minutes in high-leverage matchups."
    elif minutes_per_game >= 26 and assists_per_game >= 4:
        label = "Playmaking Guard"
        summary = "Orchestrates the offense and creates high-quality looks for teammates."
    elif minutes_per_game >= 22 and usage_proxy >= 9 and defense_proxy >= 2:
        label = "Two-Way Contributor"
        summary = "Balances scoring responsibilities with active defensive involvement."
    elif minutes_per_game >= 16:
        label = "Rotation Contributor"
        summary = "Provides dependable minutes and helps stabilize the rotation."
    else:
        label = "Situational Contributor"
        summary = "Steps into targeted roles based on matchup needs and lineup balance."

    if points_per_game >= 15:
        summary = "Drives the attack with consistent scoring and a steady offensive presence."
    elif assists_per_game >= 5:
        summary = "Keeps the offense organized and elevates teammates with consistent playmaking."
    elif defense_proxy >= 3.2:
        summary = "Impacts games through defensive activity and control of the glass."

    return label, summary


# Prior-season lookup for delta calculations.
def get_prior_season(selected_season, season_list):
    if not selected_season or not season_list:
        return None
    ordered = sorted(season_list, key=season_sort_key)
    if selected_season not in ordered:
        return None
    idx = ordered.index(selected_season)
    if idx == 0:
        return None
    return ordered[idx - 1]


# Build a subtle delta indicator (direction + percentage).
def build_delta_indicator(stat_name, current_value, previous_value, negative_stats):
    if current_value is None or previous_value in (None, 0):
        return ""
    delta_pct = (current_value - previous_value) / abs(previous_value) * 100
    if abs(delta_pct) < 0.5:
        direction = "neutral"
        arrow = "."
    else:
        is_positive = delta_pct > 0
        if stat_name in negative_stats:
            is_positive = not is_positive
        direction = "positive" if is_positive else "negative"
        arrow = "^" if delta_pct > 0 else "v"
    delta_text = f"{arrow} {abs(delta_pct):.1f}%"
    return f"""<span class="impact-stat-delta {direction}">{delta_text}</span>"""


# Generate short trend bullets across multiple seasons.
def build_trajectory_summary(trend_df):
    if trend_df is None or len(trend_df) < 2:
        return []
    trend_df = trend_df.sort_values("Season Sort")
    first = trend_df.iloc[0]
    last = trend_df.iloc[-1]

    metrics = []
    for label, key, higher_is_better, fmt in [
        ("Usage load", "Usage Proxy", True, "{:.1f}"),
        ("Efficiency", "Efficiency", True, "{:.3f}"),
        ("Control", "Control", False, "{:.2f}"),
    ]:
        start = first.get(key)
        end = last.get(key)
        if start in (None, 0) or end is None:
            continue
        pct_change = (end - start) / abs(start) * 100
        metrics.append(
            {
                "label": label,
                "start": start,
                "end": end,
                "pct_change": pct_change,
                "higher_is_better": higher_is_better,
                "fmt": fmt,
            }
        )

    if not metrics:
        return []

    metrics = sorted(metrics, key=lambda x: abs(x["pct_change"]), reverse=True)
    bullets = []
    for metric in metrics[:2]:
        change_direction = "increased" if metric["pct_change"] > 2 else "decreased" if metric["pct_change"] < -2 else "held steady"
        start_fmt = metric["fmt"].format(metric["start"])
        end_fmt = metric["fmt"].format(metric["end"])
        bullets.append(
            f"{metric['label']} has {change_direction} from {start_fmt} to {end_fmt} across the available seasons."
        )
    return bullets

player_tags = []
if "2020-21" in player_seasons:
    player_tags.append("COVID Player")
current_season = str(df_illinois_stats["Season"].max())
if current_season in player_seasons:
    player_tags.append("Current Player")



# Player header block.

divider(PRIMARY)

col_image, col_text, col_geo = st.columns([1.5, 2, 4])
with col_image:
    if 'Jersey Number' in player_header:
        name_len = len(player)
        if name_len <= 12:
            name_class = "player-name-short"
        elif name_len <= 18:
            name_class = "player-name-medium"
        else:
            name_class = "player-name-long"
        st.markdown(
            f"""
            <div class="player-jersey-line">
                <span class="player-jersey-number {name_class}"># {player_header['Jersey Number']} - </span>
                <span class="player-jersey-name {name_class}" style="color:{PRIMARY};">{player}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown('<div class="player-text-marker"></div>', unsafe_allow_html=True)
    # Player image.
    if 'Image URL' in player_header:
        image_src = player_header['Image URL']
    else:
        image_src = image_to_data_uri("data\images\illini_no_image.webp")

    icon_map = {
        "Instagram URL": "data/images/instagram.png",
        "Twitter URL": "data/images/X.png",
        "NIL URL": "data/images/NIL.webp",
    }
    icon_links = []
    for key, value in player_header.items():
        if "URL" in key and key != "Image URL" and value and key in icon_map:
            icon_links.append((icon_map[key], value))

    icon_html = ""
    if icon_links:
        icon_items = []
        for icon_path, url in icon_links:
            icon_uri = image_to_data_uri(icon_path)
            icon_items.append(
                f"""<a class="player-icon-link" href="{url}" target="_blank" rel="noopener noreferrer">
                    <img src="{icon_uri}" />
                </a>
                """
            )
        icon_html = f"""<div class="player-icon-links">{''.join(icon_items)}</div>"""

    # Separate blocks so you can copy/paste into any column.
    image_html = f"""
    <div class="player-image-stack">
        <div class="player-card">
            <img src="{image_src}" />
        </div>
    </div>
    """

    st.markdown(image_html, unsafe_allow_html=True)

    
with col_text:
    if 'Class' in player_header:
        # Class / year display.
        st.markdown(
            f"""<h3><span style='color:black'>{player_header['Class']} </span></h3>""",
            unsafe_allow_html=True,
        )
    info_lines = []
    if 'Height' in player_header:
        info_lines.append(f"<p><strong>Height:</strong> {player_header['Height']}</p>")
    if 'Weight' in player_header:
        info_lines.append(f"<p><strong>Weight:</strong> {player_header['Weight']} lbs</p>")
    if 'Position' in player_header:
        info_lines.append(f"<p><strong>Position:</strong> {player_header['Position']}</p>")
    if 'Major' in player_header:
        info_lines.append(f"<p><strong>Major:</strong> {player_header['Major']}</p>")
    if 'Hometown' in player_header:
        info_lines.append(f"<p><strong>Hometown:</strong> {player_header['Hometown']}</p>")
    if 'High School' in player_header:
        info_lines.append(f"<p><strong>High School:</strong> {player_header['High School']}</p>")
    if 'Prev School' in player_header:
        info_lines.append(f"<p><strong>Previous School:</strong> {player_header['Prev School']}</p>")
    if info_lines:
        st.markdown(
            f"""<div class="player-text-card">{''.join(info_lines)}</div>""",
            unsafe_allow_html=True,
        )
    else:
        st.info("No player info available.")

    icon_html = ""
    if icon_links:
        icon_items = []
        for icon_path, url in icon_links:
            icon_uri = image_to_data_uri(icon_path)
            icon_items.append(
                f"""<a class="player-icon-link" href="{url}" target="_blank" rel="noopener noreferrer">
                    <img src="{icon_uri}" />
                </a>
                """
            )
        icon_html = f"""<div class="player-icon-links">{''.join(icon_items)}</div>"""
        st.markdown(icon_html, unsafe_allow_html=True)

    if player_tags:
        tag_items = "".join([f'<span class="player-tag">{tag}</span>' for tag in player_tags])
        tags_html = f"""<div class="player-tags">{tag_items}</div>"""
        st.markdown(tags_html, unsafe_allow_html=True)
        
with col_geo:
    st.markdown('<div class="player-map-title">Hometown Map</div>', unsafe_allow_html=True)
    geo = player_data.get("geocode", {})
    lat = geo.get("lat")
    lon = geo.get("lon")
    if lat is not None and lon is not None:
        map_df = pd.DataFrame(
            [
                {
                    "lat": lat,
                    "lon": lon,
                    "label": geo.get("hometown", player_header.get("Hometown", "Hometown")),
                }
            ]
        )
        zoom = 6.2 if geo.get("is_illinois") else 4.2
        view_state = pdk.ViewState(latitude=lat, longitude=lon, zoom=zoom, pitch=35)
        layer = pdk.Layer(
            "ScatterplotLayer",
            data=map_df,
            get_position="[lon, lat]",
            get_fill_color="[255, 123, 0, 170]",
            get_radius=45000,
            radius_min_pixels=6,
            radius_max_pixels=18,
            pickable=True,
        )
        deck = pdk.Deck(
            layers=[layer],
            initial_view_state=view_state,
            map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
            tooltip={"text": "{label}"},
        )
        st.pydeck_chart(deck, width="stretch", height=380)
    else:
        st.info("No geocode data available for this player.")

# Assemble per-season player stats into one frame.
player_stats_dir = Path("data/processed/player_stats")
season_rows = []
for season in player_seasons:
    season_path = player_stats_dir / f"{season}.csv"
    if not season_path.exists():
        continue
    season_df = pd.read_csv(season_path)
    player_row = season_df[season_df["Player"] == player]
    if player_row.empty:
        continue
    row = player_row.iloc[0].copy()
    row["Season"] = season
    season_rows.append(row)

if season_rows:
    stats_df = pd.DataFrame(season_rows)
    stats_df = stats_df.rename(columns={"Player": "Player"})
    stats_cols = ["Season", "Player"] + [col for col in stats_df.columns if col not in ("Season", "Player")]
    stats_df = stats_df[stats_cols]

    numeric_cols = [col for col in stats_df.columns if col not in ("Season", "Player")]
    stats_df[numeric_cols] = stats_df[numeric_cols].apply(pd.to_numeric, errors="coerce")
    available_seasons = stats_df["Season"].tolist()
else:
    stats_df = pd.DataFrame()
    stats_cols = []
    numeric_cols = []
    available_seasons = []

role_row = None
latest_available_season = None
if not stats_df.empty and available_seasons:
    latest_available_season = sorted(available_seasons, key=season_sort_key)[-1]
    role_row = stats_df[stats_df["Season"] == latest_available_season]
    if not role_row.empty:
        role_row = role_row.iloc[0].to_dict()

# Role summary (latest season) and contribution badges (team share).
if role_row:
    role_label, role_summary = role_label_and_summary(role_row)
    contribution_badges = []
    if latest_available_season:
        team_row = df_illinois_stats[df_illinois_stats["Season"] == latest_available_season]
        if not team_row.empty:
            team_row = team_row.iloc[0]
            team_points = team_row.get("Total Points")
            team_assists = team_row.get("Total Assists")
            team_steals = team_row.get("Total Steals")
            if team_points and role_row.get("PTS") is not None:
                share = safe_divide(role_row.get("PTS"), team_points)
                if share is not None:
                    contribution_badges.append(f"Share of team points: {share:.0%}")
            if team_assists and role_row.get("AST") is not None:
                share = safe_divide(role_row.get("AST"), team_assists)
                if share is not None:
                    contribution_badges.append(f"Share of team assists: {share:.0%}")
            if team_steals and role_row.get("STL") is not None:
                share = safe_divide(role_row.get("STL"), team_steals)
                if share is not None:
                    contribution_badges.append(f"Share of team steals: {share:.0%}")

    badge_html = ""
    if contribution_badges:
        badge_html = f"""
        <div class="role-summary-badges">
            {''.join([f'<span class="role-summary-badge">{badge}</span>' for badge in contribution_badges])}
        </div>
        """

    st.markdown(
        f"""
        <div class="role-summary-card">
            <div class="role-summary-title">{role_label}</div>
            <div class="role-summary-text">{role_summary}</div>
            {badge_html}
        </div>
        """,
        unsafe_allow_html=True,
    )

# Career totals block with season span header.
divider(PRIMARY)

career_label = "Career Totals"
if available_seasons:
    ordered_seasons = sorted(available_seasons, key=season_sort_key)
    start_year = season_sort_key(ordered_seasons[0])
    end_year = season_sort_key(ordered_seasons[-1]) + 1
    if start_year and end_year:
        career_label = f"Career Totals: {start_year}-{end_year}"

st.subheader(career_label)
if stats_df.empty:
    st.info("No season stats available for this player.")
else:
    total_gp = stats_df["GP"].sum() if "GP" in stats_df.columns else None
    total_minutes = stats_df["Minutes TOT"].sum() if "Minutes TOT" in stats_df.columns else None
    total_pts = stats_df["PTS"].sum() if "PTS" in stats_df.columns else None
    total_fgm = stats_df["FGM"].sum() if "FGM" in stats_df.columns else None
    total_fga = stats_df["FGA"].sum() if "FGA" in stats_df.columns else None
    total_3pt = stats_df["3PT"].sum() if "3PT" in stats_df.columns else None
    total_3pta = stats_df["3PTA"].sum() if "3PTA" in stats_df.columns else None
    total_ftm = stats_df["FTM"].sum() if "FTM" in stats_df.columns else None
    total_fta = stats_df["FTA"].sum() if "FTA" in stats_df.columns else None
    total_off = stats_df["OFF"].sum() if "OFF" in stats_df.columns else None
    total_def = stats_df["DEF"].sum() if "DEF" in stats_df.columns else None
    total_reb = stats_df["Rebounds TOT"].sum() if "Rebounds TOT" in stats_df.columns else None
    total_ast = stats_df["AST"].sum() if "AST" in stats_df.columns else None
    total_stl = stats_df["STL"].sum() if "STL" in stats_df.columns else None
    total_blk = stats_df["BLK"].sum() if "BLK" in stats_df.columns else None

    gp_safe = total_gp if total_gp and total_gp > 0 else None
    career_fg_pct = (total_fgm / total_fga) if total_fgm is not None and total_fga else None
    career_3pt_pct = (total_3pt / total_3pta) if total_3pt is not None and total_3pta else None
    career_ft_pct = (total_ftm / total_fta) if total_ftm is not None and total_fta else None

    career_avg_minutes = (total_minutes / gp_safe) if total_minutes is not None and gp_safe else None
    career_avg_pts = (total_pts / gp_safe) if total_pts is not None and gp_safe else None
    career_avg_reb = (total_reb / gp_safe) if total_reb is not None and gp_safe else None
    career_avg_ast = (total_ast / gp_safe) if total_ast is not None and gp_safe else None
    career_avg_stl = (total_stl / gp_safe) if total_stl is not None and gp_safe else None
    career_avg_blk = (total_blk / gp_safe) if total_blk is not None and gp_safe else None

    # Totals displayed in the career grid.
    totals_stats = [
        ("Games", "GP", total_gp),
        ("Minutes", "Minutes TOT", total_minutes),
        ("Points", "PTS", total_pts),
        ("Rebounds", "Rebounds TOT", total_reb),
        ("Assists", "AST", total_ast),
        ("Steals", "STL", total_stl),
        ("Blocks", "BLK", total_blk),
    ]
    totals_cards = [
        f"""
        <div class="career-stat-card">
            <div class="career-stat-label">{label}</div>
            <div class="career-stat-value">{format_stat_value(stat_key, value)}</div>
        </div>
        """
        for label, stat_key, value in totals_stats
    ]
    st.markdown(
        f"""
        <div class="career-summary-grid">
            {''.join(totals_cards)}
        </div>
        """,
        unsafe_allow_html=True,
    )

divider(PRIMARY)

# Tabs for the impact ring and group details.
tab_styler(PRIMARY, SECONDARY, "#FFFFFF")

st.subheader("Player Impact")
if stats_df.empty:
    st.info("No season stats available for this player.")
else:
    stat_label_map = {
        "GP": "Games Played",
        "GS": "Games Started",
        "Minutes AVG": "Minutes (Avg)",
        "Minutes TOT": "Minutes (Total)",
        "FGM": "Field Goals Made",
        "FGA": "Field Goal Attempts",
        "FG%": "Field Goal %",
        "3PT": "3-Pointers Made",
        "3PTA": "3-Point Attempts",
        "3PT%": "3-Point %",
        "FTM": "Free Throws Made",
        "FTA": "Free Throw Attempts",
        "FT%": "Free Throw %",
        "PTS": "Points",
        "Scoring AVG": "Points (Avg)",
        "OFF": "Offensive Rebounds",
        "DEF": "Defensive Rebounds",
        "Rebounds AVG": "Rebounds (Avg)",
        "Rebounds TOT": "Rebounds (Total)",
        "AST": "Assists",
        "STL": "Steals",
        "BLK": "Blocks",
        "TO": "Turnovers",
        "PF": "Personal Fouls",
    }
    # Season selection drives the impact ring and detail cards.
    selected_seasons = st.multiselect(
        "Select Season(s)",
        options=available_seasons,
        default=available_seasons,
    )

    if not selected_seasons:
        st.info("Select at least one season to view the Impact Ring.")
    else:
        selected_stats = stats_df[stats_df["Season"].isin(selected_seasons)]
        summary_row = selected_stats[numeric_cols].mean()
        comparison_df = build_comparison_df(selected_seasons, player_stats_dir)

        stat_groups = [
            {
                "name": "Primary Impact",
                "color": "#FF5F05",
                "cols": ["GP", "GS", "Minutes AVG", "Minutes TOT", "FGA"],
                "invert": [],
            },
            {
                "name": "Efficiency",
                "color": "#B04D1C",
                "cols": ["PTS", "Scoring AVG", "FG%", "3PT%", "FT%"],
                "invert": [],
            },
            {
                "name": "Defense",
                "color": "#623B34",
                "cols": ["OFF", "DEF", "Rebounds AVG", "Rebounds TOT"],
                "invert": [],
            },
            {
                "name": "Discipline / Control",
                "color": "#13294B",
                "cols": ["AST", "STL", "BLK", "TO", "PF"],
                "invert": ["TO", "PF"],
            },
        ]

        # Compute normalized group scores for the ring.
        group_scores = []
        for group in stat_groups:
            values = []
            for col_name in group["cols"]:
                if col_name not in summary_row.index:
                    continue
                normalized = normalized_value(summary_row[col_name], col_name, comparison_df)
                if normalized is None:
                    continue
                if col_name in group["invert"]:
                    normalized = 1 - normalized
                values.append(normalized)
            if values:
                score = round(sum(values) / len(values) * 100, 1)
            else:
                score = None
            group_scores.append(score)

        center = 100
        radius = 68
        segment_angle = 80
        gap_angle = 10
        base_start = -90

        # Build SVG segments + legend entries.
        arc_items = []
        legend_items = []
        for idx, group in enumerate(stat_groups):
            start = base_start + idx * (segment_angle + gap_angle)
            end = start + segment_angle
            score = group_scores[idx]
            display_score = f"{score:.0f}" if score is not None else "—"
            fill_end = start + (segment_angle * (score / 100)) if score is not None else start

            base_path = arc_path(center, center, radius, start, end)
            fill_path = arc_path(center, center, radius, start, fill_end) if score not in (None, 0) else ""

            tooltip = f"{group['name']}: {display_score}"
            arc_items.append(
                f"""
                <g class="impact-arc">
                    <title>{tooltip}</title>
                    <path class="impact-arc-base" d="{base_path}" />
                    {f'<path class="impact-arc-fill" d="{fill_path}" style="stroke: {group["color"]};" />' if fill_path else ''}
                </g>
                """
            )

            legend_items.append(
                f"""
                <div class="impact-legend-item">
                    <span class="impact-legend-swatch" style="background: {group['color']};"></span>
                    <div>
                        <div class="impact-legend-label">{group['name']}</div>
                        <div class="impact-legend-score">{display_score}</div>
                    </div>
                </div>
                """
            )

        selected_label = ", ".join(selected_seasons)
        ring_html_raw = textwrap.dedent(
            f"""
            <div class="impact-ring-card">
                <div class="impact-ring-header">
                    <div class="impact-ring-title">Impact Ring</div>
                    <div class="impact-ring-subtitle">Selected seasons: {selected_label}</div>
                </div>
                <div class="impact-ring-body">
                    <div class="impact-ring-svg">
                        <svg viewBox="0 0 200 200" role="img" aria-label="Impact ring scores">
                            {''.join(arc_items)}
                            <text x="100" y="104" text-anchor="middle" class="impact-ring-center">
                                Impact
                            </text>
                        </svg>
                    </div>
                    <div class="impact-ring-legend">
                        {''.join(legend_items)}
                    </div>
                </div>
            </div>
            """
        )
        ring_html = "\n".join(line.lstrip() for line in ring_html_raw.splitlines()).strip()
        ring_col, cards_col = st.columns([1, 2])
        with ring_col:
            st.markdown(ring_html, unsafe_allow_html=True)
        # Static tooltips for non-obvious stats.
        tooltip_map = {
            "GP": "Games played across the selected season or seasons.",
            "GS": "Games started across the selected season or seasons.",
            "Minutes AVG": "Average minutes played per game.",
            "Minutes TOT": "Total minutes played across the season.",
            "FGA": "Field goal attempts per game or season total.",
            "FG%": "Field goal percentage, made shots divided by attempts.",
            "3PT%": "Three-point percentage, made threes divided by attempts.",
            "FT%": "Free throw percentage, made free throws divided by attempts.",
            "AST": "Assists, passes that directly lead to a made basket.",
            "STL": "Steals, defensive takeaways.",
            "BLK": "Blocks, shot attempts stopped at the rim.",
            "TO": "Turnovers, lost possessions.",
            "PF": "Personal fouls committed.",
        }

        negative_stats = {"TO", "PF"}
        delta_season = selected_seasons[0] if len(selected_seasons) == 1 else None
        delta_prior = get_prior_season(delta_season, available_seasons) if delta_season else None
        delta_current_row = None
        delta_prior_row = None
        # Only show deltas when a single season is selected and prior data exists.
        if delta_season and delta_prior:
            delta_current_row = stats_df[stats_df["Season"] == delta_season]
            delta_prior_row = stats_df[stats_df["Season"] == delta_prior]
            if delta_current_row.empty or delta_prior_row.empty:
                delta_current_row = None
                delta_prior_row = None
            else:
                delta_current_row = delta_current_row.iloc[0]
                delta_prior_row = delta_prior_row.iloc[0]

        detail_cards = []
        for idx, group in enumerate(stat_groups):
            stat_lines = []
            for col_name in group["cols"]:
                if col_name not in summary_row.index:
                    continue
                value = summary_row[col_name]
                label = stat_label_map.get(col_name, col_name)
                tooltip = tooltip_map.get(col_name)
                label_html = (
                    f'<span class="impact-stat-label" title="{tooltip}">{label}</span>'
                    if tooltip
                    else f'<span class="impact-stat-label">{label}</span>'
                )
                delta_html = ""
                if delta_current_row is not None and delta_prior_row is not None:
                    current_val = delta_current_row.get(col_name)
                    previous_val = delta_prior_row.get(col_name)
                    delta_html = build_delta_indicator(col_name, current_val, previous_val, negative_stats)
                stat_lines.append(
                    f"""
                    <div class="impact-stat-row">
                        {label_html}
                        <span class="impact-stat-value">{format_stat_value(col_name, value)}{delta_html}</span>
                    </div>
                    """
                )
            detail_cards.append(
                f"""
                <div class="impact-detail-card" style="border-left-color: {group['color']};">
                    <div class="impact-detail-header">{group['name']}</div>
                    <div class="impact-detail-body">
                        {''.join(stat_lines)}
                    </div>
                </div>
                """
            )
        details_html_raw = f"""
        <div class="impact-details-grid">
            {''.join(detail_cards)}
        </div>
        """
        details_html = "\n".join(line.lstrip() for line in details_html_raw.splitlines()).strip()
        with cards_col:
            st.markdown(details_html, unsafe_allow_html=True)

    divider(PRIMARY)
    st.subheader("Notable Season Stats and Rankings")
    # Awards and rankings section.
    if len(available_seasons) == 1:
        selected_award_season = available_seasons[0]
        st.caption(f"Awards for {selected_award_season}")
    else:
        selected_award_season = st.selectbox(
            "Select a Season",
            options=available_seasons,
            index=0,
            key="award_season_select",
        )

    season_path = player_stats_dir / f"{selected_award_season}.csv"
    if not season_path.exists():
        st.info("No award data available for this season.")
    else:
        season_df = pd.read_csv(season_path)
        season_df_numeric = season_df.copy()
        season_numeric_cols = [col for col in season_df_numeric.columns if col != "Player"]
        season_df_numeric[season_numeric_cols] = season_df_numeric[season_numeric_cols].apply(
            pd.to_numeric,
            errors="coerce",
        )
        player_season_row = season_df_numeric[season_df_numeric["Player"] == player]

        if player_season_row.empty:
            st.info("No award data available for this player in the selected season.")
        else:
            negative_stats = {"TO", "PF"}
            award_scores = []
            for col in season_numeric_cols:
                value = player_season_row.iloc[0][col]
                normalized = normalized_value(value, col, season_df_numeric)
                if normalized is None:
                    continue
                if col in negative_stats:
                    normalized = 1 - normalized
                award_scores.append(
                    {
                        "stat": col,
                        "score": normalized,
                        "value": value,
                    }
                )

            award_scores = sorted(award_scores, key=lambda x: x["score"], reverse=True)[:5]
            if not award_scores:
                st.info("No qualifying award stats were found for this player.")
            else:
                award_cols = st.columns(len(award_scores))
                for col_container, award in zip(award_cols, award_scores):
                    stat = award["stat"]
                    series = season_df_numeric[stat]
                    series = pd.to_numeric(series, errors="coerce")
                    count = series.notna().sum()
                    ascending = stat in negative_stats
                    ranks = series.rank(method="min", ascending=ascending)
                    player_rank = ranks.loc[player_season_row.index[0]]
                    if pd.isna(player_rank):
                        rank_text = f"{selected_award_season}"
                    else:
                        rank_text = f"Rank {int(player_rank)} of {int(count)}"
                    card = colored_metric(
                        label=stat_label_map.get(stat, stat),
                        value=format_stat_value(stat, award["value"]),
                        val_color=PRIMARY,
                        bg_color="white",
                        border_color="#13294B",
                        delta=f"{rank_text} • {selected_award_season}",
                        delta_b_color=SECONDARY,
                        delta_t_color="#FFFFFF",
                    )
                    with col_container:
                        st.markdown(card, unsafe_allow_html=True)

        # Build a team height comparison for the selected season.
        height_rows = []
        for name, info in data.items():
            json_file = info[2]
            with open(f"data/processed/players/{json_file}", "r") as f:
                roster_player = json.load(f)
            if selected_award_season not in roster_player.get("seasons", []):
                continue
            height_inches = roster_player.get("header", {}).get("Height Inches")
            if height_inches is None:
                continue
            height_rows.append(
                {
                    "Player": name,
                    "Height Inches": height_inches,
                    "Is Selected": name == player,
                }
            )

        height_df = pd.DataFrame(height_rows)
        if not height_df.empty:
            height_df["Height Inches"] = pd.to_numeric(height_df["Height Inches"], errors="coerce")
            height_df = height_df.dropna(subset=["Height Inches"])
            height_df = height_df.sort_values("Height Inches", ascending=True)
            player_rank = height_df.reset_index(drop=True).index[height_df["Is Selected"]]
            rank_text = ""
            if len(player_rank) > 0:
                rank_position = len(height_df) - int(player_rank[0])
                player_height = height_df[height_df["Is Selected"]]["Height Inches"].iloc[0]
                rank_text = f": {player} is <span style='color:{PRIMARY}; font-weight:700;'>#{rank_position}</span> in height at <span style='color:{PRIMARY}; font-weight:700;'>{player_height:.1f}</span> in"
            team_avg = height_df["Height Inches"].mean()
            st.markdown(
                f"<div class='player-map-title'>Height Rankings ({selected_award_season}){rank_text}</div>",
                unsafe_allow_html=True,
            )
            fig_height = px.bar(
                height_df,
                x="Player",
                y="Height Inches",
                color="Is Selected",
                color_discrete_map={False: "#9C9A9D", True: PRIMARY},
                title="",
                category_orders={"Player": height_df["Player"].tolist()},
            )
            fig_height.update_layout(
                showlegend=False,
                xaxis_title="",
                yaxis_title="Height (inches)",
                xaxis=dict(
                    categoryorder="array",
                    categoryarray=height_df["Player"].tolist(),
                    tickangle=15,
                ),
                hoverlabel=dict(
                    bgcolor="#f4f4f4",
                    bordercolor=SECONDARY,
                    font=dict(color=SECONDARY, size=12),
                ),
            )
            fig_height.update_traces(marker_line_width=0, hovertemplate=None)
            fig_height.add_hline(
                y=team_avg,
                line_dash="dash",
                line_color=SECONDARY,
                annotation_text=f"Team Avg ({team_avg:.1f} in)",
                annotation_position="top left",
            )
            st.plotly_chart(fig_height, width="stretch")
    # Multi-season normalized trend charts.
    if len(stats_df) > 1:
        divider(PRIMARY)
        all_years = stats_df[numeric_cols].mean().to_dict()
        all_years["Season"] = "All Years"
        all_years["Player"] = player
        all_years_df = pd.DataFrame([all_years])[stats_cols]
        all_years_full_df = pd.concat([all_years_df, stats_df], ignore_index=True)[stats_cols]
        comparison_df_all = build_comparison_df(available_seasons, player_stats_dir)

        st.subheader("All Years Summary")

        group_tabs = st.tabs([group["name"] for group in stat_groups])
        for tab, group in zip(group_tabs, stat_groups):
            with tab:
                normalized_rows = []
                for _, row in stats_df.iterrows():
                    season_label = row["Season"]
                    for col_name in group["cols"]:
                        if col_name not in row.index:
                            continue
                        normalized = normalized_value(row[col_name], col_name, comparison_df_all)
                        if normalized is None:
                            continue
                        if col_name in group["invert"]:
                            normalized = 1 - normalized
                        normalized_rows.append(
                            {
                                "Season": season_label,
                                "Stat": col_name,
                                "Normalized": normalized,
                            }
                        )
                normalized_df = pd.DataFrame(normalized_rows)
                fig_group = px.line(
                    normalized_df,
                    x="Season",
                    y="Normalized",
                    color="Stat",
                    line_dash="Stat",
                    title=f"{group['name']} (Normalized Stats by Season)",
                    markers=True,
                    color_discrete_sequence=[group["color"]],
                )
                fig_group.update_traces(mode="markers+lines", hovertemplate=None)
                fig_group.update_layout(
                    hovermode="x",
                    yaxis=dict(range=[0, 1], title="Normalized Value", tickformat=".0%"),
                    hoverlabel=dict(
                        bgcolor="#f4f4f4",
                        bordercolor=SECONDARY,
                        font=dict(color=SECONDARY, size=12),
                    ),
                )
                st.plotly_chart(fig_group, width="stretch")

if "2020-21" in player_seasons:
    st.info("Note: The 2020-21 season was impacted by COVID-19, which may affect player statistics and comparisons.")

# Development trajectory summary (text-only, hidden if one season).
trajectory_rows = []
if len(stats_df) > 1:
    for _, row in stats_df.iterrows():
        season_label = row.get("Season")
        usage_proxy = compute_usage_proxy(row)
        efficiency = row.get("FG%")
        if efficiency is None:
            efficiency = safe_divide(row.get("PTS"), row.get("FGA"))
        control = safe_divide(row.get("TO"), row.get("GP"))
        if control is None:
            control = safe_divide(row.get("PF"), row.get("GP"))
        trajectory_rows.append(
            {
                "Season": season_label,
                "Season Sort": season_sort_key(season_label),
                "Usage Proxy": usage_proxy,
                "Efficiency": efficiency,
                "Control": control,
            }
        )

trajectory_df = pd.DataFrame(trajectory_rows)
trajectory_bullets = build_trajectory_summary(trajectory_df)
if trajectory_bullets:
    divider(PRIMARY)
    st.markdown(
        f"""
        <div class="trajectory-card">
            <div class="trajectory-title">Development Trajectory</div>
            <ul class="trajectory-list">
                {''.join([f'<li>{bullet}</li>' for bullet in trajectory_bullets])}
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


# Optional action photo carousel.
action_photos = player_data.get("action photos", [])
if action_photos:
    divider(PRIMARY)
    st.subheader("Action Photos")
    slide_seconds = 4
    total_duration = max(len(action_photos), 1) * slide_seconds
    slide_items = []
    for idx, photo in enumerate(action_photos):
        url = photo.get("url")
        if not url:
            continue
        credit = photo.get("credit")
        credit_html = f'<div class="carousel-caption">{credit}</div>' if credit else ""
        slide_html = textwrap.dedent(
            f"""
            <div class="carousel-slide" style="animation-delay: {idx * slide_seconds}s;">
                <img src="{url}" alt="{player} action photo {idx + 1}" />
                {credit_html}
            </div>
            """
        ).strip()
        slide_items.append(slide_html)
    shell_class = "carousel-shell single" if len(slide_items) == 1 else "carousel-shell"
    carousel_html_raw = f"""
    <div class="{shell_class}" style="--carousel-duration: {total_duration}s;">
        {''.join(slide_items)}
    </div>
    """
    carousel_html = "\n".join(line.lstrip() for line in carousel_html_raw.splitlines()).strip()
    st.markdown(carousel_html, unsafe_allow_html=True)

team_season_set = set(seasons)
available_player_seasons = [s for s in player_seasons if s in team_season_set]
with st.sidebar:
    st.markdown(
        f"""
        <div class="sidebar-overview">
            <div class="sidebar-player-label">Player Dashboard</div>
            <div class="sidebar-player-name" style="color:{PRIMARY};">{player}</div>
            <h4>What you'll find</h4>
            <ul class="sidebar-section-list">
                <li>Profile, role summary, and player tags</li>
                <li>Impact ring and detailed stat breakdowns</li>
                <li>Season awards, rankings, and comparisons</li>
                <li>Height ranking and team context views</li>
                <li>All-years trend lines and development notes</li>
                <li>Action photo carousel (when available)</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.subheader("Team Overview Seasons")
    st.markdown(
        """
        <style>
        section[data-testid="stSidebar"] div[data-testid="stButton"] > button {
            padding: 0.6rem 1.1rem;
            border-radius: 999px;
            font-weight: 700;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    if available_player_seasons:
        for season_label in sorted(available_player_seasons, key=season_sort_key, reverse=True):
            if st.button(season_label, key=f"sidebar_team_overview_{player}_{season_label}"):
                st.session_state["selected_season"] = season_label
                st.switch_page("pages/2_Team_Overviews.py")
    else:
        st.caption("No season history available for this player.")

divider(PRIMARY)
st.subheader("Explore More Pages!")
st.markdown(
    """
    There are multiple ways to dive into the statistics behind the **Illini Men's Basketball Team**.
    Use the buttons below to travel to the corresponding page!
    """
)
nan1, left, nan3, right, nan2 = st.columns([0.25, 2, 0.5, 2, 0.25])
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
with right:
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
