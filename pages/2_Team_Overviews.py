import json
import random
import re
import textwrap
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.components import colored_metric, divider, load_theme_colors, tab_styler
from utils.data import history_csvs, load_css, image_to_data_uri
from utils.player_dashboard import arc_path, normalized_value

st.set_page_config(page_title="Team Overviews", layout="wide")

# Load shared visual styles.
load_css(
    "styles/base.css",
    "styles/layout.css",
    "styles/cards.css",
    "styles/player_dashboard.css",
)

st.markdown(
    """
    <style>
    .team-hero {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 10px;
        text-align: center;
        margin-top: 6px;
        margin-bottom: 10px;
    }
    .team-hero-name {
        font-family: "Space Grotesk", "Montserrat", "Helvetica Neue", Arial, sans-serif;
        font-weight: 700;
        font-size: clamp(26px, 2.6vw, 40px);
        letter-spacing: -0.4px;
        margin: 0;
    }
    .team-hero-records {
        display: flex;
        flex-wrap: wrap;
        gap: 14px;
        justify-content: center;
    }
    .team-hero-record {
        padding: 8px 14px;
        border-radius: 999px;
        background: rgba(19, 41, 75, 0.08);
        color: #111111;
        font-size: 0.95rem;
        font-weight: 600;
    }
    .wm-metric-card {
        border: 1px solid rgba(19, 41, 75, 0.18);
    }
    .team-compare-card {
        padding: 16px 18px;
        border-radius: 18px;
        background: var(--card-overlay), var(--card-bg);
        box-shadow: var(--shadow-1), var(--shadow-2);
    }
    .team-compare-row {
        display: grid;
        grid-template-columns: 1.4fr 1fr 1fr 1fr;
        gap: 12px;
        padding: 10px 0;
        border-bottom: 1px solid rgba(15, 30, 51, 0.08);
        align-items: center;
    }
    .team-compare-row:last-child {
        border-bottom: none;
    }
    .team-compare-stat {
        font-weight: 600;
        color: #1b1b1b;
    }
    .team-compare-illini {
        font-weight: 700;
        text-align: right;
    }
    .team-compare-opp {
        color: #7a7a7a;
        font-weight: 600;
        text-align: right;
    }
    .team-roster-card {
        border-radius: 14px;
        background: var(--card-overlay), var(--card-bg);
        box-shadow: var(--shadow-1), var(--shadow-2);
        padding: 8px 10px 12px 10px;
        transition: transform 0.18s ease, box-shadow 0.18s ease;
        height: 100%;
        margin-bottom: 12px;
    }
    .team-roster-card:hover {
        transform: translateY(-3px) scale(1.01);
        box-shadow: 0 16px 45px rgba(16, 24, 40, 0.16), 0 4px 12px rgba(16, 24, 40, 0.10);
    }
    .team-roster-img-wrap {
        width: 100%;
        aspect-ratio: 3 / 4;
        border-radius: 12px;
        overflow: hidden;
        background: #f2f2f4;
    }
    .team-roster-img-wrap > img.team-roster-img {
        display: block;
        width: 100% !important;
        height: 100% !important;
        max-width: 100% !important;
        border-radius: 12px;
        object-fit: cover !important;
        object-position: center !important;
    }
    .team-roster-name {
        margin: 6px 0 2px 0;
        font-size: 0.92rem;
        font-weight: 700;
        color: #111111;
    }
    .team-roster-meta {
        font-size: 0.78rem;
        color: #6f6f6f;
        margin-bottom: 6px;
    }
    .team-roster-stats {
        display: flex;
        justify-content: space-between;
        font-size: 0.78rem;
        color: #2b2b2b;
    }
    .team-roster-stat span {
        font-weight: 700;
    }
    .team-roster-card div[data-testid="stButton"] > button {
        background: linear-gradient(180deg, #ffffff 0%, #f3f4f7 100%);
        border: 1px solid rgba(19, 41, 75, 0.18);
        border-radius: 999px;
        color: #13294b;
        font-weight: 700;
        font-size: 0.78rem;
        padding: 0.35rem 0.75rem;
        box-shadow: 0 2px 6px rgba(16, 24, 40, 0.08);
        transition: transform 0.16s ease, box-shadow 0.16s ease, background 0.16s ease;
        width: 100%;
    }
    .team-roster-card div[data-testid="stButton"] > button:hover {
        transform: translateY(-1px);
        background: linear-gradient(180deg, #ffffff 0%, #eef1f6 100%);
        box-shadow: 0 6px 14px rgba(16, 24, 40, 0.12);
    }
    .team-roster-button {
        margin-top: 8px;
    }
    .team-roster-button div[data-testid="stButton"] > button {
        background: linear-gradient(180deg, #ffffff 0%, #f3f4f7 100%);
        border: 1px solid rgba(19, 41, 75, 0.18);
        border-radius: 999px;
        color: #13294b;
        font-weight: 700;
        font-size: 0.78rem;
        padding: 0.35rem 0.75rem;
        box-shadow: 0 2px 6px rgba(16, 24, 40, 0.08);
        transition: transform 0.16s ease, box-shadow 0.16s ease, background 0.16s ease;
        width: 100%;
    }
    .team-roster-button div[data-testid="stButton"] > button:hover {
        transform: translateY(-1px);
        background: linear-gradient(180deg, #ffffff 0%, #eef1f6 100%);
        box-shadow: 0 6px 14px rgba(16, 24, 40, 0.12);
    }
    .team-achievement-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 14px;
    }
    .team-achievement-card {
        border-radius: 18px;
        background: var(--card-overlay), var(--card-bg);
        box-shadow: var(--shadow-1), var(--shadow-2);
        padding: 14px 16px;
        display: flex;
        gap: 12px;
        align-items: center;
    }
    .team-achievement-icon {
        width: 42px;
        height: 42px;
        border-radius: 12px;
        background: rgba(19, 41, 75, 0.12);
        color: #13294b;
        font-weight: 700;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.85rem;
        letter-spacing: 0.06em;
    }
    .team-achievement-label {
        font-size: 0.9rem;
        color: #6a6a6a;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
    .team-achievement-value {
        font-size: 1.4rem;
        font-weight: 700;
        color: #111111;
    }
    .team-impact-side {
        display: flex;
        flex-direction: column;
        gap: 14px;
    }
    .team-impact-card {
        border-radius: 22px;
        background: var(--card-overlay), var(--card-bg);
        box-shadow: var(--shadow-1), var(--shadow-2);
        padding: 22px 24px;
    }
    .team-impact-card h4 {
        margin: 0 0 10px 0;
        font-size: 1.3rem;
        color: #111111;
    }
    .team-impact-card ul {
        margin: 0;
        padding-left: 20px;
        color: #2b2b2b;
        font-size: 1.05rem;
        line-height: 1.75;
    }
    .team-leader-list {
        display: flex;
        flex-direction: column;
        gap: 10px;
    }
    .team-leader-item {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        gap: 12px;
        padding-bottom: 6px;
        border-bottom: 1px solid rgba(15, 30, 51, 0.08);
    }
    .team-leader-item:last-child {
        border-bottom: none;
        padding-bottom: 0;
    }
    .team-leader-label {
        font-size: 0.95rem;
        font-weight: 600;
        color: #2b2b2b;
    }
    .team-leader-value {
        font-size: 1.05rem;
        font-weight: 700;
        color: #111111;
    }
    .impact-ring-card {
        max-width: 100%;
        width: 100%;
        padding: 26px 30px;
        border-radius: 24px;
    }
    .impact-ring-svg {
        width: 320px;
        height: 320px;
    }
    .impact-ring-body {
        flex-direction: row;
        align-items: center;
        gap: 24px;
    }
    .impact-ring-legend {
        min-width: 220px;
        margin-left: auto;
    }
    .team-snapshot-subline {
        font-size: 0.75rem;
        color: #6f6f6f;
        margin-top: 6px;
        text-align: center;
        font-weight: 600;
    }
    .impact-legend-benchmark {
        font-size: 0.78rem;
        color: #6f6f6f;
        margin-top: 2px;
    }
    .impact-summary-card {
        border-radius: 18px;
        background: rgba(19, 41, 75, 0.06);
        padding: 14px 16px;
        color: #1b1b1b;
        font-size: 0.95rem;
        margin-top: 12px;
    }
    .team-compare-delta {
        font-weight: 700;
        text-align: right;
    }
    .team-compare-delta span {
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }
    .roster-sort-bar {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 12px;
        padding: 12px 14px;
        border-radius: 16px;
        background: rgba(19, 41, 75, 0.06);
        color: #1b1b1b;
        font-size: 0.9rem;
        font-weight: 600;
    }
    .team-roster-badge {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 2px 8px;
        border-radius: 999px;
        background: rgba(19, 41, 75, 0.12);
        color: #13294b;
        font-size: 0.68rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-top: 6px;
        min-height: 18px;
    }
    .team-roster-badge.placeholder {
        visibility: hidden;
    }
    .team-roster-card.leader {
        border: 1px solid rgba(19, 41, 75, 0.35);
    }
    .team-identity-card {
        border-radius: 20px;
        background: var(--card-overlay), var(--card-bg);
        box-shadow: var(--shadow-1), var(--shadow-2);
        padding: 20px 22px;
        font-size: 1rem;
        color: #1b1b1b;
    }
    .sidebar-overview {
        border-radius: 16px;
        padding: 16px 18px;
        background: rgba(19, 41, 75, 0.06);
        border: 1px solid rgba(19, 41, 75, 0.12);
    }
    .sidebar-overview h4 {
        margin: 0 0 10px 0;
        font-size: 1.05rem;
        letter-spacing: 0.02em;
        color: #1b1b1b;
    }
    .sidebar-season-label {
        font-size: 0.78rem;
        color: #6f6f6f;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 4px;
        font-weight: 700;
    }
    .sidebar-season-value {
        font-size: 1.25rem;
        font-weight: 800;
        margin: 0 0 12px 0;
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

# Theme palette.
THEME_COLORS = load_theme_colors()
PRIMARY = THEME_COLORS["primary"]
SECONDARY = THEME_COLORS["secondary"]

tab_styler(PRIMARY, SECONDARY, "#FFFFFF")

# Helper utilities (must be defined before data sources use them).
def filter_history_since(df: pd.DataFrame, start_year: int = 2000) -> pd.DataFrame:
    if "Season Start Year" not in df.columns:
        return df
    years = pd.to_numeric(df["Season Start Year"], errors="coerce")
    return df[years >= start_year].copy()


def percentile_rank(series: pd.Series, value, invert: bool = False):
    series = pd.to_numeric(series, errors="coerce").dropna()
    value = pd.to_numeric(value, errors="coerce")
    if series.empty or pd.isna(value):
        return None
    if invert:
        return float((series >= value).mean() * 100)
    return float((series <= value).mean() * 100)


def rank_position(series: pd.Series, value, invert: bool = False):
    series = pd.to_numeric(series, errors="coerce").dropna()
    value = pd.to_numeric(value, errors="coerce")
    if series.empty or pd.isna(value):
        return None, len(series)
    ranks = series.rank(method="min", ascending=invert)
    matching = ranks[series == value]
    if matching.empty:
        return None, len(series)
    return int(matching.min()), len(series)


def coverage_ok(series: pd.Series, min_coverage: float = 0.7) -> bool:
    series = pd.to_numeric(series, errors="coerce")
    if series.empty:
        return False
    return series.notna().mean() >= min_coverage


def format_delta(value, decimals=1, suffix=""):
    value = pd.to_numeric(value, errors="coerce")
    if value is None or pd.isna(value):
        return "--"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.{decimals}f}{suffix}"

# Data sources.
df_season_stats = pd.read_csv("data/processed/season_stats.csv")
df_illinois_stats = df_season_stats[df_season_stats["Team"] == "Illinois"].copy()
df_opponent_stats = df_season_stats[df_season_stats["Team"] == "Opponents"].copy()
df_history_base = filter_history_since(df_illinois_stats, 2000)

with open("data/processed/player_list.json", "r", encoding="utf-8") as f:
    player_list = json.load(f)


def season_sort_key(season_label: str) -> int:
    try:
        return int(str(season_label).split("-")[0])
    except (ValueError, AttributeError, IndexError):
        return 0


def safe_divide(numerator, denominator):
    if numerator in (None, 0) or denominator in (None, 0):
        return None
    return numerator / denominator


def format_record(wins, losses):
    if pd.isna(wins) or pd.isna(losses):
        return "N/A"
    return f"{int(wins)}-{int(losses)}"


def format_pct(value):
    value = pd.to_numeric(value, errors="coerce")
    if value is None or pd.isna(value):
        return "-"
    return f"{value * 100:.1f}%"


def format_number(value, decimals=1):
    value = pd.to_numeric(value, errors="coerce")
    if value is None or pd.isna(value):
        return "-"
    if isinstance(value, (int, float)):
        if decimals == 0:
            return f"{int(round(value))}"
        return f"{value:.{decimals}f}"
    return str(value)


def parse_attendance(value):
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    matches = re.findall(r"\d[\d,]*", str(value))
    if not matches:
        return None
    last = matches[-1].replace(",", "")
    try:
        return float(last)
    except ValueError:
        return None


def normalize_series(series: pd.Series):
    series = pd.to_numeric(series, errors="coerce")
    min_val = series.min()
    max_val = series.max()
    if pd.isna(min_val) or pd.isna(max_val) or max_val == min_val:
        return series * 0
    return (series - min_val) / (max_val - min_val)


seasons = sorted(df_illinois_stats["Season"].tolist(), key=season_sort_key)
latest_season = seasons[-1] if seasons else None

st.title("Team Overviews")
c_box, _ = st.columns([1.45, 4])
with c_box:
    season_options = seasons[::-1]
    selected_season = st.session_state.get("selected_season")
    if selected_season in season_options:
        season_index = season_options.index(selected_season)
    else:
        season_index = 0
    season = st.selectbox(
        label="Select a Season",
        options=season_options,
        index=season_index,
        key="season_select",
    )

with st.sidebar:
    st.markdown(
        f"""
        <div class="sidebar-overview">
            <div class="sidebar-season-label">Selected Season</div>
            <div class="sidebar-season-value" style="color:{PRIMARY};">{season}</div>
            <h4>What you'll find</h4>
            <ul class="sidebar-section-list">
                <li>Season snapshot and efficiency context</li>
                <li>Illinois vs. opponent performance comparisons</li>
                <li>Impact profile and identity summary</li>
                <li>Prior-season trends and notable awards</li>
                <li>Roster composition insights and cards</li>
                <li>Team action photo carousel</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

divider(PRIMARY)

season_row = df_illinois_stats[df_illinois_stats["Season"] == season]
opponent_row = df_opponent_stats[df_opponent_stats["Season"] == season]
season_row = season_row.iloc[0] if not season_row.empty else None
opponent_row = opponent_row.iloc[0] if not opponent_row.empty else None

overall_record = format_record(
    season_row.get("Overall Wins") if season_row is not None else None,
    season_row.get("Overall Losses") if season_row is not None else None,
)
conference_record = format_record(
    season_row.get("Conference Wins") if season_row is not None else None,
    season_row.get("Conference Losses") if season_row is not None else None,
)

st.markdown(
    f"""
    <section class="team-hero">
      <div class="team-hero-name" style="color:{PRIMARY};">
        Illinois Fighting Illini
      </div>
      <div class="team-hero-records">
        <div class="team-hero-record">{season} Season</div>
        <div class="team-hero-record">Overall: {overall_record}</div>
        <div class="team-hero-record">Conference: {conference_record}</div>
      </div>
    </section>
    """,
    unsafe_allow_html=True,
)

divider(PRIMARY)

# Season snapshot metrics.
st.subheader("Season Snapshot")
st.markdown(
    "<div style='color:#6f6f6f; font-size:0.9rem; margin-bottom: 12px;'>"
    "Quick view of the team's core outputs for the selected season."
    "</div>",
    unsafe_allow_html=True,
)
if season_row is None:
    st.info("No season stats available.")
else:
    history_df = df_history_base if not df_history_base.empty else df_illinois_stats
    snapshot_stats = [
        ("Points Per Game", "Points Per Game", season_row.get("Points Per Game"), "pts", False),
        ("Scoring Margin", "Scoring Margin", season_row.get("Scoring Margin"), "pts", False),
        ("FG%", "FG: Percentage", season_row.get("FG: Percentage"), "pct", False),
        ("3PT%", "3PT: Percentage", season_row.get("3PT: Percentage"), "pct", False),
        ("FT%", "FT: Percentage", season_row.get("FT: Percentage"), "pct", False),
        ("Rebounds Per Game", "Rebounds Per Game", season_row.get("Rebounds Per Game"), "pts", False),
        ("Assist / Turnover Ratio", "Assist/Turnover Ratio", season_row.get("Assist/Turnover Ratio"), "ratio", False),
        (
            "Attendance Per Game",
            "Attendance Per Game",
            parse_attendance(season_row.get("Attendance Per Game")),
            "attendance",
            False,
        ),
    ]

    metric_cols = st.columns(4)
    for idx, (label, col_name, value, fmt, invert) in enumerate(snapshot_stats):
        if col_name == "Attendance Per Game":
            history_series = history_df[col_name].apply(parse_attendance)
        else:
            history_series = history_df[col_name]
        percentile = percentile_rank(history_series, value, invert=invert)
        if percentile is not None:
            top_pct = max(1, int(round(100 - percentile)))
            percentile_text = f"Top {top_pct}% since 2000"
        else:
            percentile_text = "Historical rank unavailable"
        if fmt == "pct":
            display = format_pct(value)
        elif fmt == "ratio":
            display = format_number(value, decimals=2)
        elif fmt == "attendance":
            display = f"{int(value):,}" if value is not None else "-"
        else:
            display = format_number(value, decimals=1)
        card = colored_metric(
            label=label,
            value=display,
            val_color=PRIMARY,
            bg_color="white",
            border_color="#13294B",
            delta=percentile_text,
            delta_b_color="#F1F3F7",
            delta_t_color="#4a4a4a",
        )
        with metric_cols[idx % 4]:
            st.markdown(card, unsafe_allow_html=True)

divider(PRIMARY)

# Team efficiency comparison.
st.subheader("Team Efficiency Comparison")
st.markdown(
    "<div style='color:#6f6f6f; font-size:0.9rem; margin-bottom: 12px;'>"
    "Side-by-side Illinois vs opponent per-game efficiency for the selected season."
    "</div>",
    unsafe_allow_html=True,
)
comparison_stats = [
    ("FG%", "FG: Percentage"),
    ("3PT%", "3PT: Percentage"),
    ("FT%", "FT: Percentage"),
    ("Rebounds Per Game", "Rebounds Per Game"),
    ("Points Per Game", "Points Per Game"),
    ("Blocks / Steals Per Game", ("Blocks Per Game", "Steals Per Game")),
]

if season_row is None or opponent_row is None:
    st.info("No comparison data available for this season.")
else:
    rows_html = []
    rows_html.append(
        f"""
        <div class="team-compare-row" style="padding-top: 0; font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.08em; color: #6a6a6a;">
          <div class="team-compare-stat">Metric</div>
          <div class="team-compare-illini" style="color:{PRIMARY};">Illinois</div>
          <div class="team-compare-opp">Opponents</div>
        </div>
        """
    )
    for label, key in comparison_stats:
        if isinstance(key, tuple):
            illini_value = sum([season_row.get(k) or 0 for k in key])
            opp_value = sum([opponent_row.get(k) or 0 for k in key])
            illini_display = format_number(illini_value, decimals=1)
            opp_display = format_number(opp_value, decimals=1)
        else:
            illini_val = season_row.get(key)
            opp_val = opponent_row.get(key)
            if "Percentage" in key:
                illini_display = format_pct(illini_val)
                opp_display = format_pct(opp_val)
            else:
                illini_display = format_number(illini_val, decimals=1)
                opp_display = format_number(opp_val, decimals=1)
        rows_html.append(
            f"""<div class="team-compare-row">
              <div class="team-compare-stat">{label}</div>
              <div class="team-compare-illini" style="color:{PRIMARY};">{illini_display}</div>
              <div class="team-compare-opp">{opp_display}</div>
            </div>
            """
        )
    st.markdown(
        f"""
        <div class="team-compare-card">
          {''.join(rows_html)}
        </div>
        """,
        unsafe_allow_html=True,
    )

divider(PRIMARY)

# Team impact ring.
st.subheader("Team Impact Profile")
st.markdown(
    "<div style='color:#6f6f6f; font-size:0.9rem; margin-bottom: 12px;'>"
    "Four grouped scores summarize the team's identity for the season."
    "</div>",
    unsafe_allow_html=True,
)
if season_row is None:
    st.info("No impact profile data available.")
else:
    comparison_df_team = df_illinois_stats.copy()
    comparison_df_opp = df_opponent_stats.copy()
    stat_groups = [
        {
            "name": "Offensive Output",
            "color": "#FF5F05",
            "cols": ["Points Per Game", "FG: Percentage", "3PT: Percentage", "FT: Percentage"],
            "invert": [],
        },
        {
            "name": "Defensive Pressure",
            "color": "#B04D1C",
            "cols": ["Steals Per Game", "Blocks Per Game", "Opponent FG%"],
            "invert": ["Opponent FG%"],
        },
        {
            "name": "Rebounding & Physicality",
            "color": "#623B34",
            "cols": ["Rebounds Per Game", "Rebound Margin"],
            "invert": [],
        },
        {
            "name": "Ball Control",
            "color": "#13294B",
            "cols": ["Assists Per Game", "Turnovers Per Game", "Assist/Turnover Ratio"],
            "invert": ["Turnovers Per Game"],
        },
    ]

    def compute_group_scores(team_row, opp_row):
        scores = []
        for group in stat_groups:
            values = []
            for col_name in group["cols"]:
                if col_name == "Opponent FG%":
                    raw_val = opp_row.get("FG: Percentage") if opp_row is not None else None
                    raw_val = pd.to_numeric(raw_val, errors="coerce")
                    normalized = normalized_value(raw_val, "FG: Percentage", comparison_df_opp)
                else:
                    raw_val = team_row.get(col_name) if team_row is not None else None
                    raw_val = pd.to_numeric(raw_val, errors="coerce")
                    normalized = normalized_value(raw_val, col_name, comparison_df_team)
                if normalized is None:
                    continue
                if col_name in group["invert"]:
                    normalized = 1 - normalized
                values.append(normalized)
            scores.append(round(sum(values) / len(values) * 100, 1) if values else None)
        return scores

    group_scores = compute_group_scores(season_row, opponent_row)
    history_group_scores = []
    history_df = df_history_base if not df_history_base.empty else df_illinois_stats
    for _, row in history_df.iterrows():
        opp_match = comparison_df_opp[comparison_df_opp["Season"] == row.get("Season")]
        opp_row_hist = opp_match.iloc[0] if not opp_match.empty else None
        scores = compute_group_scores(row, opp_row_hist)
        history_group_scores.append(scores)

    group_averages = []
    group_percentiles = []
    for group_idx in range(len(stat_groups)):
        series_vals = [
            scores[group_idx]
            for scores in history_group_scores
            if scores and scores[group_idx] is not None
        ]
        if series_vals:
            avg_val = float(pd.Series(series_vals).mean())
            pct = percentile_rank(pd.Series(series_vals), group_scores[group_idx], invert=False)
        else:
            avg_val = None
            pct = None
        group_averages.append(avg_val)
        group_percentiles.append(pct)

    center = 100
    radius = 68
    segment_angle = 80
    gap_angle = 10
    base_start = -90

    arc_items = []
    legend_items = []
    for idx, group in enumerate(stat_groups):
        start = base_start + idx * (segment_angle + gap_angle)
        end = start + segment_angle
        score = group_scores[idx]
        display_score = f"{score:.0f}" if score is not None else "--"
        fill_end = start + (segment_angle * (score / 100)) if score not in (None, 0) else start

        pct = group_percentiles[idx]
        if pct is None:
            bucket = "No data"
        elif pct >= 85:
            bucket = "Elite"
        elif pct >= 65:
            bucket = "Above Avg"
        elif pct >= 45:
            bucket = "Avg"
        else:
            bucket = "Below Avg"
        avg_val = group_averages[idx]
        avg_label = f"Program avg {avg_val:.0f}" if avg_val is not None else "Program avg —"

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
                    <div class="impact-legend-benchmark">{bucket} | {avg_label}</div>
                </div>
            </div>
            """
        )

    ring_html_raw = textwrap.dedent(
        f"""
        <div class="impact-ring-card">
            <div class="impact-ring-header">
                <div class="impact-ring-title">Team Impact Profile</div>
                <div class="impact-ring-subtitle">Season: {season}</div>
            </div>
            <div class="impact-ring-body">
                <div class="impact-ring-svg">
                    <svg viewBox="0 0 200 200" role="img" aria-label="Team impact ring scores">
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
    ring_col, leader_col = st.columns([2.2, 1])
    with ring_col:
        st.markdown(ring_html, unsafe_allow_html=True)
    with leader_col:
        group_lookup = {group["name"]: group for group in stat_groups}
        active_group = None
        selected_group = None
        if group_scores and any(score is not None for score in group_scores):
            valid_scores = [score if score is not None else -1 for score in group_scores]
            best_idx = int(pd.Series(valid_scores).idxmax())
            selected_group = stat_groups[best_idx]["name"]
            active_group = group_lookup.get(selected_group)
        else:
            selected_group = stat_groups[0]["name"]
            active_group = group_lookup.get(selected_group)
        stat_label_map = {
            "Points Per Game": "Points / Game",
            "FG: Percentage": "FG%",
            "3PT: Percentage": "3PT%",
            "FT: Percentage": "FT%",
            "Steals Per Game": "Steals / Game",
            "Blocks Per Game": "Blocks / Game",
            "Opponent FG%": "Opponent FG%",
            "Rebounds Per Game": "Rebounds / Game",
            "Rebound Margin": "Rebound Margin",
            "Assists Per Game": "Assists / Game",
            "Turnovers Per Game": "Turnovers / Game",
            "Assist/Turnover Ratio": "Assist/TO Ratio",
        }

        stat_rows = []
        if active_group:
            for col_name in active_group["cols"]:
                if col_name == "Opponent FG%":
                    raw_val = opponent_row.get("FG: Percentage") if opponent_row is not None else None
                else:
                    raw_val = season_row.get(col_name)
                if "Percentage" in col_name or col_name == "Opponent FG%":
                    display = format_pct(raw_val)
                elif "Ratio" in col_name:
                    display = format_number(raw_val, 2)
                else:
                    display = format_number(raw_val, 1)
                stat_rows.append(
                    (
                        stat_label_map.get(col_name, col_name),
                        display,
                    )
                )

        if stat_rows:
            st.markdown(
                f"""
                <div class="team-impact-card" style="margin: 0 auto;">
                  <h4>Top Impact: {selected_group}</h4>
                  <div class="team-leader-list">
                    {''.join([f'<div class="team-leader-item"><div class="team-leader-label">{label}</div><div class="team-leader-value">{value}</div></div>' for label, value in stat_rows])}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    narrative_lines = []
    if group_scores and all(score is not None for score in group_scores):
        best_idx = int(pd.Series(group_scores).idxmax())
        worst_idx = int(pd.Series(group_scores).idxmin())
        best_name = stat_groups[best_idx]["name"]
        worst_name = stat_groups[worst_idx]["name"]
        narrative_lines.append(
            f"This team's identity was driven by {best_name.lower()} while {worst_name.lower()} "
            "lagged behind recent program norms."
        )
    if season_row is not None:
        ppg = format_number(season_row.get("Points Per Game"), 1)
        margin = format_number(season_row.get("Scoring Margin"), 1)
        if ppg != "-" and margin != "-":
            narrative_lines.append(
                f"It posted {ppg} points per game with a {margin} scoring margin."
            )
    narrative_text = " ".join(narrative_lines[:2])
    if narrative_text:
        st.markdown(
            f"""
            <div class="impact-summary-card">
              {narrative_text}
            </div>
            """,
            unsafe_allow_html=True,
        )

    takeaways = []
    if all(score is not None for score in group_scores):
        best_idx = int(pd.Series(group_scores).idxmax())
        worst_idx = int(pd.Series(group_scores).idxmin())
        takeaways.append(
            f"Best identity marker: {stat_groups[best_idx]['name']} led the profile at {group_scores[best_idx]:.0f}."
        )
        takeaways.append(
            f"Needs attention: {stat_groups[worst_idx]['name']} trailed at {group_scores[worst_idx]:.0f}."
        )
    if season_row is not None:
        ppg = format_number(season_row.get("Points Per Game"), 1)
        margin = format_number(season_row.get("Scoring Margin"), 1)
        reb_margin = format_number(season_row.get("Rebound Margin"), 1)
        takeaways.append(f"Offensive pace delivered {ppg} points per game with a {margin} scoring margin.")
        takeaways.append(f"Rebound margin sat at {reb_margin} per game for physicality context.")
    takeaways = takeaways[:4]

    if takeaways:
        st.markdown(
            f"""
            <div class="team-impact-card" style="margin-top: 14px;">
              <h4>Key Takeaways</h4>
              <ul>
                {''.join([f'<li>{t}</li>' for t in takeaways])}
              </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

divider(PRIMARY)

# Prior season comparison.
st.subheader("Prior Season Comparison")
if season_row is None or df_illinois_stats.empty:
    st.info("No prior season comparison available.")
else:
    prior_season = None
    if season in seasons:
        season_idx = seasons.index(season)
        if season_idx > 0:
            prior_season = seasons[season_idx - 1]
    if prior_season is None:
        st.info("No prior season available for comparison.")
    else:
        st.markdown(
            "<div style='color:#6f6f6f; font-size:0.9rem; margin-bottom: 12px;'>"
            f"Values for {season} vs {prior_season}."
            "</div>",
            unsafe_allow_html=True,
        )
        prior_row = df_illinois_stats[df_illinois_stats["Season"] == prior_season]
        prior_row = prior_row.iloc[0] if not prior_row.empty else None
        prior_opp_row = df_opponent_stats[df_opponent_stats["Season"] == prior_season]
        prior_opp_row = prior_opp_row.iloc[0] if not prior_opp_row.empty else None
        prior_scores = compute_group_scores(prior_row, prior_opp_row) if prior_row is not None else []
        comparison_rows = []
        metric_defs = [
            ("Points Per Game", "Points Per Game", "pts"),
            ("Scoring Margin", "Scoring Margin", "pts"),
            ("FG%", "FG: Percentage", "pct"),
            ("Rebound Margin", "Rebound Margin", "pts"),
        ]
        for label, col_name, fmt in metric_defs:
            current_val = pd.to_numeric(season_row.get(col_name), errors="coerce")
            prior_val = pd.to_numeric(prior_row.get(col_name), errors="coerce") if prior_row is not None else None
            if fmt == "pct":
                current_display = format_pct(current_val)
                prior_display = format_pct(prior_val)
            else:
                current_display = format_number(current_val, 1)
                prior_display = format_number(prior_val, 1)
            delta = current_val - prior_val if pd.notna(current_val) and pd.notna(prior_val) else None
            if fmt == "pct":
                delta_display = format_delta(delta * 100, 1, " pp") if delta is not None else "—"
            else:
                delta_display = format_delta(delta, 1) if delta is not None else "—"
            comparison_rows.append((label, current_display, prior_display, delta_display))

        if prior_scores and group_scores:
            for idx, group in enumerate(stat_groups):
                cur_score = group_scores[idx]
                prev_score = prior_scores[idx] if idx < len(prior_scores) else None
                if cur_score is None or prev_score is None:
                    continue
                delta = cur_score - prev_score
                comparison_rows.append(
                    (
                        f"{group['name']} (Impact)",
                        format_number(cur_score, 1),
                        format_number(prev_score, 1),
                        format_delta(delta, 1),
                    )
                )

        rows_html = []
        header_html = textwrap.dedent(
            f"""
            <div class="team-compare-row" style="padding-top: 0; font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.08em; color: #6a6a6a;">
              <div class="team-compare-stat">Metric</div>
              <div class="team-compare-illini" style="color:{PRIMARY};">{season}</div>
              <div class="team-compare-opp">{prior_season}</div>
              <div class="team-compare-delta">Percent Change</div>
            </div>
            """
        ).strip()
        for label, current_display, prior_display, delta_display in comparison_rows:
            rows_html.append(
                textwrap.dedent(
                    f"""
                    <div class="team-compare-row">
                      <div class="team-compare-stat">{label}</div>
                      <div class="team-compare-illini" style="color:{PRIMARY};">{current_display}</div>
                      <div class="team-compare-opp">{prior_display}</div>
                      <div class="team-compare-delta">{delta_display}</div>
                    </div>
                    """
                ).strip()
            )
        if rows_html:
            st.markdown(
                textwrap.dedent(
                    f"""
                    <div class="team-compare-card">
                      {header_html}
                      {''.join(rows_html)}
                    </div>
                    """
                ).strip(),
                unsafe_allow_html=True,
            )
        else:
            st.info("No prior season metrics available for comparison.")

st.subheader("Team Identity Summary")
st.markdown(
    "<div style='color:#6f6f6f; font-size:0.9rem; margin-bottom: 12px;'>"
    "A synthesized view of how this season is remembered."
    "</div>",
    unsafe_allow_html=True,
)
identity_lines = []
if season_row is not None:
    best_group_name = None
    if group_scores and all(score is not None for score in group_scores):
        best_idx = int(pd.Series(group_scores).idxmax())
        best_group_name = stat_groups[best_idx]["name"].lower()
    ppg = format_number(season_row.get("Points Per Game"), 1)
    fg_pct = format_pct(season_row.get("FG: Percentage"))
    margin = format_number(season_row.get("Scoring Margin"), 1)
    if best_group_name and ppg != "-" and margin != "-":
        identity_lines.append(
            f"The {season} Illinois team leaned on {best_group_name}, scoring {ppg} points "
            f"per game with a {fg_pct} FG% and a {margin} scoring margin."
        )
    elif ppg != "-" and margin != "-":
        identity_lines.append(
            f"The {season} Illinois team scored {ppg} points per game with a {fg_pct} FG% "
            f"and a {margin} scoring margin."
        )
    history_df = df_history_base if not df_history_base.empty else df_illinois_stats
    rank, total = rank_position(history_df["Scoring Margin"], season_row.get("Scoring Margin"))
    if rank:
        identity_lines.append(
            f"That margin ranked {rank} of {total} among Illinois seasons since 2000."
        )

identity_text = " ".join(identity_lines[:3]) if identity_lines else ""
if identity_text:
    st.markdown(
        f"""
        <div class="team-identity-card">
          {identity_text}
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    st.info("No identity summary available for this season.")

divider(PRIMARY)

# Season awards & notable stats.
st.subheader("Season Awards & Notable Stats")
st.markdown(
    "<div style='color:#6f6f6f; font-size:0.9rem; margin-bottom: 12px;'>"
    "Highlights where this season stands among other Illinois seasons."
    "</div>",
    unsafe_allow_html=True,
)
if season_row is None or df_illinois_stats.empty:
    st.info("No season comparisons available.")
else:
    compare_stats = [
        ("Points Per Game", "Points Per Game", False, "pts"),
        ("Scoring Margin", "Scoring Margin", False, "pts"),
        ("FG%", "FG: Percentage", False, "pct"),
        ("3PT%", "3PT: Percentage", False, "pct"),
        ("FT%", "FT: Percentage", False, "pct"),
        ("Rebounds / Game", "Rebounds Per Game", False, "pts"),
        ("Assists / Game", "Assists Per Game", False, "pts"),
        ("Turnovers / Game", "Turnovers Per Game", True, "pts"),
        ("Attendance / Game", "Attendance Per Game", False, "attendance"),
    ]

    def stat_rank(series, value, invert):
        series = pd.to_numeric(series, errors="coerce").dropna()
        if series.empty or value is None or pd.isna(value):
            return None, len(series)
        ascending = invert
        ranks = series.rank(method="min", ascending=ascending)
        matching = ranks[series == value]
        if matching.empty:
            return None, len(series)
        return int(matching.min()), len(series)

    notable_scores = []
    for label, col_name, invert, fmt in compare_stats:
        raw_val = season_row.get(col_name)
        if col_name == "Attendance Per Game":
            raw_val = parse_attendance(raw_val)
        value = pd.to_numeric(raw_val, errors="coerce")
        if col_name == "Attendance Per Game":
            attendance_series = df_illinois_stats[col_name].apply(parse_attendance)
            min_val = attendance_series.min()
            max_val = attendance_series.max()
            if pd.isna(value) or pd.isna(min_val) or pd.isna(max_val) or max_val == min_val:
                normalized = None
            else:
                normalized = (value - min_val) / (max_val - min_val)
        else:
            normalized = normalized_value(value, col_name, df_illinois_stats)
        if normalized is None:
            continue
        if invert:
            normalized = 1 - normalized
        if fmt == "pct":
            display = format_pct(value)
        elif fmt == "attendance":
            display = f"{int(value):,}" if value is not None and not pd.isna(value) else "-"
        else:
            display = format_number(value, 1)
        if col_name == "Attendance Per Game":
            rank, total = stat_rank(attendance_series, value, invert)
        else:
            rank, total = stat_rank(df_illinois_stats[col_name], value, invert)
        notable_scores.append(
            {
                "label": label,
                "display": display,
                "score": normalized,
                "rank": rank,
                "total": total,
            }
        )

    notable_scores = sorted(notable_scores, key=lambda x: x["score"], reverse=True)[:6]
    if notable_scores:
        card_cols = st.columns(3)
        for idx, item in enumerate(notable_scores):
            delta_text = (
                f"Rank {item['rank']} of {item['total']} Seasons"
                if item["rank"]
                else f"Score {item['score']:.0%}"
            )
            card = colored_metric(
                label=item["label"],
                value=item["display"],
                val_color=PRIMARY,
                bg_color="white",
                border_color="#13294B",
                delta=delta_text,
                delta_b_color=SECONDARY,
                delta_t_color="#FFFFFF",
            )
            with card_cols[idx % 3]:
                st.markdown(card, unsafe_allow_html=True)
    else:
        st.info("No notable season stats available for comparison.")

# Season-specific program achievements (only shown when earned that year).
season_awards = []
season_start_year = season_row.get("Season Start Year") if season_row is not None else None
season_end_year = None
if season:
    try:
        season_end_year = int(str(season).split("-")[0]) + 1
    except (ValueError, IndexError, TypeError):
        season_end_year = None
award_sources = [
    (
        "NCAA Tournament Appearance",
        "NCAA",
        "data/processed/mbb_history_csv/35_NCAA_Tournament_Appearances.csv",
    ),
    ("Final Four", "FF", "data/processed/mbb_history_csv/5_NCAA_Final_Fours.csv"),
    ("National Title", "NT", "data/processed/mbb_history_csv/1_National_Title.csv"),
    (
        "Big Ten Regular Season Champs",
        "B10",
        "data/processed/mbb_history_csv/18_Big_Ten_Regular_Season_Championships.csv",
    ),
    (
        "Big Ten Tournament Champs",
        "B10T",
        "data/processed/mbb_history_csv/4_Big_Ten_Tournament_Championships.csv",
    ),
]

season_award_year = season_end_year or season_start_year
if season_award_year is not None:
    for label, icon_text, path in award_sources:
        df_years = history_csvs(path)
        years = df_years["Year"].tolist() if "Year" in df_years.columns else []
        if season_award_year in years:
            season_awards.append((label, icon_text))

if season_awards:
    divider(PRIMARY)
    st.subheader(f"Program Achievements ({season})")
    st.markdown(
        "<div style='color:#6f6f6f; font-size:0.9rem; margin-bottom: 12px;'>"
        "Program milestones earned specifically in this season."
        "</div>",
        unsafe_allow_html=True,
    )
    achievement_html = []
    for label, icon_text in season_awards:
        achievement_html.append(
            f"""<div class="team-achievement-card">
              <div class="team-achievement-icon">{icon_text}</div>
              <div>
                <div class="team-achievement-label">{label}</div>
                <div class="team-achievement-value">Earned</div>
              </div>
            </div>
            """
        )

    st.markdown(
        f"""
        <div class="team-achievement-grid">
          {''.join(achievement_html)}
        </div>
        """,
        unsafe_allow_html=True,
    )

divider(PRIMARY)

# Roster composition insights.
st.subheader("Roster Composition Insights")
st.markdown(
    "<div style='color:#6f6f6f; font-size:0.9rem; margin-bottom: 12px;'>"
    "Breakdown of roster build, size, and class makeup for the season."
    "</div>",
    unsafe_allow_html=True,
)
roster_headers = []
for player_name, info in player_list.items():
    seasons_played = info[1] if len(info) > 1 else []
    if season not in seasons_played:
        continue
    json_file = info[2]
    json_path = Path("data/processed/players") / json_file
    if not json_path.exists():
        continue
    with open(json_path, "r", encoding="utf-8") as f:
        player_data = json.load(f)
    header = player_data.get("header", {})
    roster_headers.append(header)

height_values = [h.get("Height Inches") for h in roster_headers if h.get("Height Inches") is not None]
height_series = pd.to_numeric(pd.Series(height_values), errors="coerce").dropna()
avg_height = height_series.mean() if not height_series.empty else None

class_order = ["Freshman", "Sophomore", "Junior", "Senior", "Graduate Student"]
class_counts = {cls: 0 for cls in class_order}
for header in roster_headers:
    cls = header.get("Class")
    if cls in class_counts:
        class_counts[cls] += 1
    else:
        class_counts.setdefault(cls, 0)
        class_counts[cls] += 1

transfer_count = 0
homegrown_count = 0
for header in roster_headers:
    prev_school = header.get("Prev School")
    if prev_school and str(prev_school).strip():
        transfer_count += 1
    else:
        homegrown_count += 1

underclassmen = class_counts.get("Freshman", 0) + class_counts.get("Sophomore", 0)
upperclassmen = (
    class_counts.get("Junior", 0)
    + class_counts.get("Senior", 0)
    + class_counts.get("Graduate Student", 0)
)
summary_bits = []
if upperclassmen or underclassmen:
    if upperclassmen > underclassmen:
        summary_bits.append(
            f"This roster skewed upperclassmen-heavy with {upperclassmen} upperclassmen "
            f"versus {underclassmen} underclassmen."
        )
    elif underclassmen > upperclassmen:
        summary_bits.append(
            f"This roster skewed underclassmen-heavy with {underclassmen} underclassmen "
            f"versus {upperclassmen} upperclassmen."
        )
    else:
        summary_bits.append(
            f"This roster split evenly between {upperclassmen} upperclassmen and {underclassmen} underclassmen."
        )
if transfer_count or homegrown_count:
    summary_bits.append(
        f"It featured {transfer_count} transfers and {homegrown_count} homegrown players."
    )
if avg_height:
    summary_bits.append(f"Average height checked in at {format_number(avg_height, 1)} inches.")
roster_summary = " ".join(summary_bits[:2])

if roster_summary:
    st.markdown(
        f"""
        <div class="impact-summary-card" style="margin-bottom: 12px;">
          {roster_summary}
        </div>
        """,
        unsafe_allow_html=True,
    )

left_col, right_col = st.columns(2)
with left_col:
    st.markdown(
        f"**Average Height:** {format_number(avg_height, 1)} in"
        if avg_height
        else "**Average Height:** N/A"
    )
    if not height_series.empty:
        fig_height = px.histogram(
            x=height_series,
            nbins=8,
            labels={"x": "Height (inches)", "y": "Players"},
        )
        fig_height.update_traces(marker_color=PRIMARY, hovertemplate=None)
        fig_height.update_layout(
            title="Height Distribution",
            showlegend=False,
            bargap=0.12,
            hovermode="x",
            hoverlabel=dict(
                bgcolor="#f4f4f4",
                bordercolor=SECONDARY,
                font=dict(color=SECONDARY, size=12),
            ),
        )
        if avg_height:
            fig_height.add_vline(
                x=avg_height,
                line_dash="dash",
                line_color=SECONDARY,
                annotation_text=f"Avg {avg_height:.1f} in",
                annotation_position="top left",
            )
        fig_height.update_layout(height=460)
        st.plotly_chart(fig_height, width="stretch", height=460)
        st.markdown(
            "<div style='text-align:center; color:#6f6f6f; font-size:0.85rem;'>"
            "Distribution of roster heights for the selected season. Dashed line shows the team average."
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        st.info("No height data available for this roster.")

with right_col:
    class_df = pd.DataFrame(
        {"Class": list(class_counts.keys()), "Players": list(class_counts.values())}
    )
    if not class_df.empty and class_df["Players"].sum() > 0:
        max_class_count = class_df["Players"].max()
        top_classes = class_df[class_df["Players"] == max_class_count]["Class"].tolist()
        top_classes = [cls for cls in top_classes if cls and not pd.isna(cls)]
        if top_classes:
            preferred_order = class_order + [cls for cls in top_classes if cls not in class_order]
            ordered_top = [cls for cls in preferred_order if cls in top_classes]
            top_label = ", ".join(str(cls) for cls in ordered_top)
            st.markdown(f"**Most Common Class:** {top_label}")
        else:
            st.markdown("**Most Common Class:** N/A")
        fig_class = px.bar(
            class_df,
            x="Class",
            y="Players",
            color_discrete_sequence=[PRIMARY],
        )
        fig_class.update_traces(marker_line_width=0, hovertemplate=None)
        fig_class.update_layout(
            title="Class Distribution",
            showlegend=False,
            hoverlabel=dict(
                bgcolor="#f4f4f4",
                bordercolor=SECONDARY,
                font=dict(color=SECONDARY, size=12),
            ),
        )
        fig_class.update_layout(height=460)
        st.plotly_chart(fig_class, width="stretch", height=460)
        st.markdown(
            "<div style='text-align:center; color:#6f6f6f; font-size:0.85rem;'>"
            "Roster class counts (Freshman through Graduate Student) for the selected season."
            "</div>",
            unsafe_allow_html=True,
        )

transfer_df = pd.DataFrame(
    {
        "Group": ["Transfers", "Homegrown"],
        "Players": [transfer_count, homegrown_count],
    }
)
fig_transfer = px.bar(
    transfer_df,
    x="Group",
    y="Players",
    color_discrete_sequence=[SECONDARY],
)
fig_transfer.update_traces(marker_line_width=0, hovertemplate=None)
fig_transfer.update_layout(
    title="Transfers vs Homegrown",
    showlegend=False,
    hoverlabel=dict(
        bgcolor="#f4f4f4",
        bordercolor=SECONDARY,
        font=dict(color=SECONDARY, size=12),
    ),
)

center_left, center_col, center_right = st.columns([1, 2, 1])
with center_col:
    st.plotly_chart(fig_transfer, width="stretch")
    st.markdown(
        "<div style='text-align:center; color:#6f6f6f; font-size:0.85rem;'>"
        "Counts players with a previous school listed as transfers; others are treated as Illinois recruits."
        "</div>",
        unsafe_allow_html=True,
    )

divider(PRIMARY)

# Roster overview.
st.subheader("Roster Overview")
st.markdown(
    "<div style='color:#6f6f6f; font-size:0.9rem; margin-bottom: 12px;'>"
    "Current roster cards with quick per-game production for this season."
    "</div>",
    unsafe_allow_html=True,
)
player_stats_path = Path("data/processed/player_stats") / f"{season}.csv"
player_stats_df = pd.read_csv(player_stats_path) if player_stats_path.exists() else pd.DataFrame()
if not player_stats_df.empty:
    player_stats_df["Player"] = player_stats_df["Player"].astype(str).str.strip()
    for col in player_stats_df.columns:
        if col != "Player":
            player_stats_df[col] = pd.to_numeric(player_stats_df[col], errors="coerce")

roster_cards = []
for player_name, info in player_list.items():
    seasons_played = info[1] if len(info) > 1 else []
    if season not in seasons_played:
        continue
    json_file = info[2]
    json_path = Path("data/processed/players") / json_file
    if not json_path.exists():
        continue
    with open(json_path, "r", encoding="utf-8") as f:
        player_data = json.load(f)
    header = player_data.get("header", {})
    image_url = header.get("Image URL") or image_to_data_uri("data/images/illini_no_image.webp")
    jersey = header.get("Jersey Number", "")
    position = header.get("Position", "")
    player_class = header.get("Class", "")
    player_stats = (
        player_stats_df[player_stats_df["Player"] == player_name]
        if not player_stats_df.empty
        else pd.DataFrame()
    )
    if not player_stats.empty:
        row = player_stats.iloc[0]
        points = row.get("Scoring AVG")
        if pd.isna(points):
            points = safe_divide(row.get("PTS"), row.get("GP"))
        minutes = row.get("Minutes AVG")
        if pd.isna(minutes):
            minutes = safe_divide(row.get("Minutes TOT"), row.get("GP"))
        rebounds = row.get("Rebounds AVG")
        if pd.isna(rebounds):
            rebounds = safe_divide(row.get("Rebounds TOT"), row.get("GP"))
        assists = safe_divide(row.get("AST"), row.get("GP"))
    else:
        points = minutes = rebounds = assists = None

    roster_cards.append(
        {
            "name": player_name,
            "image_url": image_url,
            "jersey": jersey,
            "position": position,
            "class": player_class,
            "pts": points,
            "mins": minutes,
            "reb": rebounds,
            "ast": assists,
        }
    )

if not roster_cards:
    st.info("No roster data available for this season.")
else:
    def jersey_sort_key(card):
        jersey = str(card.get("jersey", "")).strip()
        return int(jersey) if jersey.isdigit() else 9999

    default_roster = sorted(roster_cards, key=jersey_sort_key)
    leader_badges = {}
    leader_priority = [
        ("Scoring Leader", "pts"),
        ("Minutes Leader", "mins"),
        ("Rebounding Leader", "reb"),
        ("Assist Leader", "ast"),
    ]
    for badge_label, key in leader_priority:
        values = [card.get(key) for card in roster_cards if card.get(key) is not None]
        if not values:
            continue
        max_val = max(values)
        for card in roster_cards:
            if card.get(key) == max_val and card["name"] not in leader_badges:
                leader_badges[card["name"]] = badge_label

    sort_choice = st.radio(
        "Sort roster cards by",
        [
            "Default (Jersey #)",
            "Points per game",
            "Minutes per game",
            "Rebounds per game",
            "Assists per game",
        ],
        horizontal=True,
    )
    if sort_choice == "Points per game":
        roster_cards = sorted(roster_cards, key=lambda x: x["pts"] or 0, reverse=True)
    elif sort_choice == "Minutes per game":
        roster_cards = sorted(roster_cards, key=lambda x: x["mins"] or 0, reverse=True)
    elif sort_choice == "Rebounds per game":
        roster_cards = sorted(roster_cards, key=lambda x: x["reb"] or 0, reverse=True)
    elif sort_choice == "Assists per game":
        roster_cards = sorted(roster_cards, key=lambda x: x["ast"] or 0, reverse=True)
    else:
        roster_cards = list(default_roster)

    num_cols = 6
    roster_cols = st.columns(num_cols)
    for idx, card in enumerate(roster_cards):
        col = roster_cols[idx % num_cols]
        with col:
            badge = leader_badges.get(card["name"])
            if badge:
                badge_html = f'<div class="team-roster-badge">{badge}</div>'
            else:
                badge_html = '<div class="team-roster-badge placeholder">Leader</div>'
            leader_class = "leader" if badge else ""
            st.markdown(
                f"""
                <div class="team-roster-card {leader_class}">
                  <div class="team-roster-img-wrap">
                    <img class="team-roster-img" src="{card['image_url']}" alt="{card['name']} headshot" />
                  </div>
                  <div class="team-roster-name">{card['name']} {f"#{card['jersey']}" if card['jersey'] else ""}</div>
                  <div class="team-roster-meta">{card['position']} {card['class']}</div>
                  <div class="team-roster-stats">
                    <div class="team-roster-stat">PTS <span>{format_number(card['pts'], 1)}</span></div>
                    <div class="team-roster-stat">REB <span>{format_number(card['reb'], 1)}</span></div>
                    <div class="team-roster-stat">AST <span>{format_number(card['ast'], 1)}</span></div>
                  </div>
                  {badge_html}
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(
                "View Profile",
                key=f"player_profile_{idx}",
                help=f"Open {card['name']} in the Player Dashboard",
                width="stretch",
            ):
                st.session_state["selected_player"] = card["name"]
                st.switch_page("pages/3_Player_Dashboards.py")

divider(PRIMARY)

# Team action photo carousel.
action_photo_urls = []
season_roster_names = [card["name"] for card in roster_cards] if "roster_cards" in globals() else []
if not season_roster_names:
    for player_name, info in player_list.items():
        seasons_played = info[1] if len(info) > 1 else []
        if season in seasons_played:
            season_roster_names.append(player_name)

seen_action_urls = set()
for player_name in season_roster_names:
    player_info = player_list.get(player_name)
    if not player_info or len(player_info) < 3:
        continue
    json_file = player_info[2]
    json_path = Path("data/processed/players") / json_file
    if not json_path.exists():
        continue
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            player_data = json.load(f)
    except Exception:
        continue
    player_photos = player_data.get("action photos", []) or []
    for photo in player_photos:
        if isinstance(photo, dict):
            url = photo.get("url")
        else:
            url = photo
        if url and url not in seen_action_urls:
            seen_action_urls.add(url)
            action_photo_urls.append(url)

if action_photo_urls:
    st.subheader("Team Action")
    st.markdown(
        "<div style='color:#6f6f6f; font-size:0.9rem; margin-bottom: 12px;'>"
    "A quick visual of the team's energy and identity."
        "</div>",
        unsafe_allow_html=True,
    )
    random.shuffle(action_photo_urls)
    hero_photos = action_photo_urls[:6]
    slide_seconds = 4
    total_duration = max(len(hero_photos), 1) * slide_seconds
    slide_items = []
    for idx, url in enumerate(hero_photos):
        if not url:
            continue
        slide_items.append(
            textwrap.dedent(
                f"""
                <div class="carousel-slide" style="animation-delay: {idx * slide_seconds}s;">
                    <img src="{url}" alt="Illinois action photo {idx + 1}" />
                </div>
                """
            ).strip()
        )
    shell_class = "carousel-shell single" if len(slide_items) == 1 else "carousel-shell"
    carousel_html = f"""
    <div class="{shell_class}" style="--carousel-duration: {total_duration}s;">
        {''.join(slide_items)}
    </div>
    """
    st.markdown(carousel_html, unsafe_allow_html=True)

divider(PRIMARY)

# Warnings for data context.
if season == "2020-21":
    st.info(
        "The 2020-21 season was impacted by COVID-19, which may affect team statistics and comparisons."
    )
if season == latest_season:
    st.info("This season may still be in progress, so stats could be incomplete or outdated.")

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
