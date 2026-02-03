import streamlit as st
import pandas as pd
from pathlib import Path
import json
import re
import random
from datetime import datetime
import plotly.express as px
from utils.components import colored_metric, divider, load_theme_colors, tab_styler
from utils.data import history_csvs, load_css, image_to_data_uri

st.set_page_config(page_title="Illini Mens Basketball Dashboard", 
                   layout="wide")

# load data
with open("data/processed/player_list.json", "r") as f:
    player_list_data = json.load(f)

THEME_COLORS = load_theme_colors()
PRIMARY = THEME_COLORS['primary']
SECONDARY = THEME_COLORS['secondary']
SUCCESS = THEME_COLORS['success']
WARNING = THEME_COLORS['warning']
MUTED = THEME_COLORS['muted']

load_css(
    "styles/base.css",
    "styles/layout.css",
    "styles/cards.css",
    "styles/player_dashboard.css",
    "styles/home.css"
)

st.markdown(
    """
    <style>
    .sidebar-overview {
        border-radius: 16px;
        padding: 16px 18px;
        background: rgba(19, 41, 75, 0.06);
        border: 1px solid rgba(19, 41, 75, 0.12);
    }
    .sidebar-home-label {
        font-size: 0.78rem;
        color: #6f6f6f;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 4px;
        font-weight: 700;
    }
    .sidebar-home-title {
        font-size: 1.2rem;
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
    .wm-dataset-card {
        position: relative;
        overflow: hidden;
    }
    .wm-update-pill {
        position: absolute;
        bottom: 12px;
        right: 12px;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        padding: 4px 10px;
        border-radius: 999px;
        background: rgba(19, 41, 75, 0.1);
        color: #13294b;
        border: 1px solid rgba(19, 41, 75, 0.2);
        opacity: 0;
        transform: translateY(4px);
        transition: opacity 0.16s ease, transform 0.16s ease;
        pointer-events: none;
    }
    .wm-dataset-card:hover .wm-update-pill,
    .wm-dataset-card:focus-within .wm-update-pill {
        opacity: 1;
        transform: translateY(0);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown(
        f"""
        <div class="sidebar-overview">
            <div class="sidebar-home-label">Home</div>
            <div class="sidebar-home-title" style="color:{PRIMARY};">Illini MBB Dashboard</div>
            <h4>What you'll find</h4>
            <ul class="sidebar-section-list">
                <li>Program overview and dataset scale</li>
                <li>All-time leaders across key stats</li>
                <li>Program trends and season charts</li>
                <li>Historic milestones and highlights</li>
                <li>Winningest seasons tables</li>
                <li>Dataset dictionary and page links</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

  
# load season stats df
df_season_stats = pd.read_csv("data/processed/season_stats.csv")
df_illinois_season = df_season_stats[df_season_stats['Team'] == "Illinois"].reset_index()

def parse_start_year(season_label):
    try:
        return int(str(season_label).split("-")[0])
    except (ValueError, TypeError, AttributeError):
        return None

def season_range_from_files(pattern):
    years = []
    for path in Path(pattern).parent.glob(Path(pattern).name):
        year = parse_start_year(path.stem)
        if year is not None:
            years.append(year)
    if not years:
        return None, None
    return min(years), max(years)

def season_range_from_years(values):
    years = [parse_start_year(v) for v in values]
    years = [y for y in years if y is not None]
    if not years:
        return None, None
    return min(years), max(years)

def format_year_range(min_year, max_year):
    if min_year is None or max_year is None:
        return "N/A"
    return f"{min_year}-{max_year}"

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

player_season_values = []
for entry in player_list_data.values():
    seasons = entry[1] if len(entry) > 1 else []
    player_season_values.extend(seasons)

player_min_year, player_max_year = season_range_from_years(player_season_values)
player_season_span = None
if player_min_year is not None and player_max_year is not None:
    player_season_span = player_max_year - player_min_year + 1

player_stats_min_year, player_stats_max_year = season_range_from_files("data/processed/player_stats/*.csv")
team_stats_min_year = int(df_season_stats["Season Start Year"].min())
team_stats_max_year = int(df_season_stats["Season Start Year"].max())

history_years = []
for history_path in Path("data/processed/mbb_history_csv").glob("*.csv"):
    df_history = history_csvs(str(history_path))
    if "Year" in df_history.columns:
        history_years.extend(df_history["Year"].tolist())
history_min_year, history_max_year = season_range_from_years(history_years)

player_stats_dir = Path("data/processed/player_stats")
player_stats_frames = []
for stats_path in sorted(player_stats_dir.glob("*.csv")):
    try:
        frame = pd.read_csv(stats_path)
    except Exception:
        continue
    frame["Season"] = stats_path.stem
    player_stats_frames.append(frame)

if player_stats_frames:
    player_stats_all = pd.concat(player_stats_frames, ignore_index=True)
    player_stats_all["Player"] = player_stats_all["Player"].astype(str).str.strip()
    player_stats_all = player_stats_all[player_stats_all["Player"] != "TeamTMTeam"]
    numeric_cols = [col for col in player_stats_all.columns if col not in ("Player", "Season")]
    for col in numeric_cols:
        player_stats_all[col] = pd.to_numeric(player_stats_all[col], errors="coerce")
    player_career_totals = player_stats_all.groupby("Player", as_index=False)[numeric_cols].sum(numeric_only=True)
else:
    player_career_totals = pd.DataFrame()

def top_career_leader(totals_df: pd.DataFrame, stat_col: str):
    if totals_df.empty or stat_col not in totals_df.columns:
        return None
    series = totals_df[stat_col]
    if series.dropna().empty:
        return None
    row = totals_df.loc[series.idxmax()]
    return row["Player"], row[stat_col]

action_photo_urls = []
action_photos_path = Path("data/images/action_photos.json")
if action_photos_path.exists():
    try:
        with open(action_photos_path, "r", encoding="utf-8") as f:
            action_photo_urls = json.load(f) or []
    except Exception:
        action_photo_urls = []


if action_photo_urls:
    random.shuffle(action_photo_urls)
    hero_photos = action_photo_urls[:8]
    slide_count = len(hero_photos)
    slide_duration = 6
    total_duration = slide_duration * slide_count
    slides_html = "\n".join(
        f"<img src=\"{url}\" style=\"animation-delay: {idx * slide_duration}s\" />"
        for idx, url in enumerate(hero_photos)
    )
    st.markdown(
        f"""
<section class="wm-hero" style="--wm-hero-duration: {total_duration}s; --wm-hero-title-color: #f4f4f4;">
  <div class="wm-hero-slides">
    {slides_html}
  </div>
  <div class="wm-hero-text">
    <div class="wm-hero-title">
      <h1>Illini Men's Basketball Dashboard</h1>
    </div>
    <p class="wm-hero-sub">An Interactive Explorer and Statistical Analysis</p>
    <p class="wm-hero-author">By Colin Bertrand</p>
  </div>
</section>
""",
        unsafe_allow_html=True,
    )
else:
    st.markdown(f"<h1 style='text-align:center; color:{PRIMARY}'>Illini Men's Basketball Dashboard</h1>", unsafe_allow_html=True)
    st.markdown("<h4 style='text-align:center;'>An interactive explorer of the Illinois Men's Basketball Team</h3>", unsafe_allow_html=True)
    st.markdown("<h5 style='text-align:center;'>By Colin Bertrand</h3>", unsafe_allow_html=True)

divider(SECONDARY)

image1 = image_to_data_uri("data/images/mbb_banner.webp")
image2 = image_to_data_uri("data/images/mbb_court.webp")
st.markdown(f"""
<section class="wm-feature">
  <div class="wm-feature-text">
    <h3>Welcome!</h3>
    <p>
        This dashboard explores the legacy of Illinois Men's Basketball
        through decades of recorded matches and statistics.
    </p>
    <p>
      Through players, seasons, achievements, and geographic context, this dashboard showcases what has shaped the program over time.
    </p>
    <p>
      The metrics below highlight the scale of the dataset, while the dashboard transforms raw history into engaging insights 
      and a demonstration of applied data science.
    </p>
  </div>

  <div class="wm-feature-img">
    <img class="wm-img-top" src="{image1}" />
    <img class="wm-img-bottom" src="{image2}" />
  </div>
</section>
""", unsafe_allow_html=True)

divider(SECONDARY)

st.subheader("Program at a Glance")
st.markdown("The Illini Men's Basketball data has the following characteristics:")
one, two, three, four = st.columns(4)

with one:
    team_count = len(df_illinois_season)
    m1 = colored_metric("Total Seasons Covered", f"{team_count} Seasons", val_color=PRIMARY, bg_color="white", border_color="#13294B",
                        delta=f"{df_illinois_season['Season Start Year'].iloc[0]} - {df_illinois_season['Season Start Year'].iloc[-1]}",
                        delta_b_color=SECONDARY, delta_t_color="#FFFFFF")
    st.markdown(m1, unsafe_allow_html=True)
with two:
    player_count = len(player_list_data)
    m2 = colored_metric("Total Players in Program History", f"{player_count} Players", val_color=PRIMARY, 
                        delta=f"Across {player_season_span} Seasons" if player_season_span else "Across N/A Seasons",
                        delta_b_color=SECONDARY, delta_t_color="#FFFFFF", 
                        bg_color="white", border_color="#13294B")
    st.markdown(m2, unsafe_allow_html=True)
with three:
    path = "data/processed/mbb_history_csv/35_NCAA_Tournament_Appearances.csv"
    df_tournament_years = history_csvs(path)
    tournament_appearances = len(df_tournament_years)
    m3 = colored_metric("Total Tournament Appearances", f"{tournament_appearances} Appearances", 
                        val_color=PRIMARY, bg_color="white", border_color="#13294B",
                        delta=f"Most Recent: {df_tournament_years['Year'].iloc[-1]}", delta_b_color=SECONDARY, delta_t_color="#FFFFFF")
    st.markdown(m3, unsafe_allow_html=True)
with four:
    path = "data/processed/mbb_history_csv/4_Big_Ten_Tournament_Championships.csv"
    df_champ_years = history_csvs(path)
    champ_years = len(df_champ_years)
    m4 = colored_metric("Total Big Ten Championships", f"{champ_years} Championships", 
                        val_color=PRIMARY, bg_color="white", border_color="#13294B",
                        delta=f"Most Recent: {df_champ_years['Year'].iloc[-1]}", delta_b_color=SECONDARY, delta_t_color="#FFFFFF")
    st.markdown(m4, unsafe_allow_html=True)

st.subheader("All-Time Leaders")
st.markdown(
    f"Career totals across {format_year_range(player_stats_min_year, player_stats_max_year)} seasons in the dataset."
)

leader_stats = [
    {"label": "Most Minutes", "stat": "Minutes TOT"},
    {"label": "Most Points", "stat": "PTS"},
    {"label": "Most Rebounds", "stat": "Rebounds TOT"},
    {"label": "Most Assists", "stat": "AST"},
    {"label": "Most Steals", "stat": "STL"},
    {"label": "Most Blocks", "stat": "BLK"},
]

if player_career_totals.empty:
    st.info("No player stat files are available yet to compute all-time leaders.")
else:
    leader_cards = []
    for leader in leader_stats:
        result = top_career_leader(player_career_totals, leader["stat"])
        if not result:
            continue
        leader_name, leader_value = result
        value_display = f"{int(leader_value):,}" if pd.notna(leader_value) else "-"
        seasons = []
        player_entry = player_list_data.get(leader_name)
        if player_entry and len(player_entry) > 1:
            seasons = player_entry[1] or []
        seasons_min, seasons_max = season_range_from_years(seasons)
        seasons_range = format_year_range(seasons_min, seasons_max)
        seasons_html = (
            f"<span class=\"wm-year-pill\">{seasons_range}</span>"
            if seasons_min is not None and seasons_max is not None
            else ""
        )
        leader_cards.append(
            f"""
<div class="wm-leader-card">
  <div class="wm-leader-label">{leader['label']}</div>
  <div class="wm-leader-player">{leader_name}</div>
  <div class="wm-leader-value">{value_display}</div>
  <div class="wm-leader-seasons">
    {seasons_html}
  </div>
</div>
"""
        )
    if leader_cards:
        st.markdown(f"<section class=\"wm-leader-grid\">{''.join(leader_cards)}</section>", unsafe_allow_html=True)
    else:
        st.info("No qualifying leaders were found in the player stats.")

divider(SECONDARY)


st.subheader("Program Trends")

tab_styler(PRIMARY, SECONDARY, "#FFFFFF")

tab_points, tab_ppg, tab_attendance, tab_record = st.tabs(["Points Per Season", "Points Per Game", "Season Attendance", "Season Wins/Losses"])

with tab_points:
    fig_points = px.line(
        df_season_stats,
        x="Season Start Year",
        y="Total Points",
        color="Team",
        color_discrete_map={
            "Illinois": PRIMARY,
            "Opponents": SECONDARY
        },
        title="Points Per Season",
        markers=True
    )
    fig_points.update_traces(mode="markers+lines", hovertemplate=None)
    fig_points.update_layout(hovermode="x",
                          hoverlabel=dict(
                          bgcolor="#f4f4f4",
                          bordercolor=SECONDARY,
                          font=dict(color=SECONDARY, size=12)))
    st.plotly_chart(fig_points, width="stretch")
    st.caption("""
               This plot reflects the trend in total points scored each season. Final data point 
               may be lower if the season is still ongoing.
               """)

with tab_ppg:
    fig_ppg = px.line(
        df_season_stats,
        x="Season Start Year",
        y="Points Per Game",
        color="Team",
        color_discrete_map={
            "Illinois": PRIMARY,
            "Opponents": SECONDARY
        },
        title="Points Per Game",
        markers=True
    )
    fig_ppg.update_traces(mode="markers+lines", hovertemplate=None)
    fig_ppg.update_layout(hovermode="x",
                          hoverlabel=dict(
                          bgcolor="#f4f4f4",
                          bordercolor=SECONDARY,
                          font=dict(color=SECONDARY, size=12)))
    st.plotly_chart(fig_ppg, width="stretch")
    st.caption("""
               This plot reflects the trend in average points scored each season. Final data point 
               may be lower if the season is still ongoing.
               """)

with tab_attendance:
    fig_att = px.line(
        df_season_stats, 
        x="Season Start Year",
        y="Total Attendance",
        color="Team",
        color_discrete_map={
            "Illinois": PRIMARY,
            "Opponents": SECONDARY
        },
        title="Season Attendance",
        markers=True
    )
    fig_att.update_traces(mode="markers+lines", hovertemplate=None)
    fig_att.update_layout(hovermode="x",
                          hoverlabel=dict(
                          bgcolor="#f4f4f4",
                          bordercolor=SECONDARY,
                          font=dict(color=SECONDARY, size=12)))
    st.plotly_chart(fig_att, width="stretch")
    st.caption("""
               This plot reflects the trend in number of fans attending the games across a season. Final data point 
               may be lower if the season is still ongoing.
               """)

with tab_record:
    record_view = st.radio(
        "Record view",
        ["Overall", "Conference"],
        horizontal=True,
        label_visibility="collapsed",
    )
    if record_view == "Overall":
        record_cols = ["Season Start Year", "Overall Wins", "Overall Losses"]
        chart_title = "Illinois Overall Record"
        c_map = {
            "Overall Wins": PRIMARY,
            "Overall Losses": SECONDARY
        }
    else:
        record_cols = ["Season Start Year", "Conference Wins", "Conference Losses"]
        chart_title = "Illinois Conference Record"
        c_map = {
            "Conference Wins": PRIMARY, 
            "Conference Losses": SECONDARY
        }

    df_records = df_illinois_season[record_cols].copy()
    record_long = df_records.melt(
        id_vars=["Season Start Year"],
        var_name="Metric",
        value_name="Value",
    )
    fig_rec = px.line(
        record_long,
        x="Season Start Year",
        y="Value",
        color="Metric",
        color_discrete_map=c_map,
        title=chart_title,
        markers=True
    )
    fig_rec.update_traces(mode="markers+lines", hovertemplate=None)
    fig_rec.update_layout(hovermode="x",
                          hoverlabel=dict(
                          bgcolor="#f4f4f4",
                          bordercolor=SECONDARY,
                          font=dict(color=SECONDARY, size=12)))
    st.plotly_chart(fig_rec, width="stretch")  
    st.caption("""
               This plot reflects the total wins for each season. Final data point 
               may be lower if the season is still ongoing. Switch between **Conference** and 
               **Overall** season wins with the buttons above the chart.
               """)

divider(SECONDARY)

st.subheader("Program History Highlights")
st.markdown("Key program milestones and achievements across Illini history:")

st.markdown(
    """
    <style>
      .wm-card-grid .wm-history-item.wm-card-wide {
        grid-column: span 2;
      }
      .wm-history-item .wm-history-years {
        margin-top: 0;
        max-height: 0;
        overflow: hidden;
        opacity: 0;
        transform: translateY(4px);
        transition: opacity 0.15s ease, transform 0.15s ease, max-height 0.15s ease, margin-top 0.15s ease;
      }
      .wm-history-item:hover .wm-history-years,
      .wm-history-item:active .wm-history-years {
        opacity: 1;
        transform: translateY(0);
        margin-top: 8px;
        max-height: 92px;
        overflow: auto;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

history_cards = [
    {
        "title": "National Titles",
        "path": "data/processed/mbb_history_csv/1_National_Title.csv",
    },
    {
        "title": "Big Ten Regular Season Championships",
        "path": "data/processed/mbb_history_csv/18_Big_Ten_Regular_Season_Championships.csv",
    },
    {
        "title": "Big Ten Tournament Championships",
        "path": "data/processed/mbb_history_csv/4_Big_Ten_Tournament_Championships.csv",
    },
    {
        "title": "NCAA Final Fours",
        "path": "data/processed/mbb_history_csv/5_NCAA_Final_Fours.csv",
    },
    {
        "title": "NCAA Tournament Appearances",
        "path": "data/processed/mbb_history_csv/35_NCAA_Tournament_Appearances.csv",
    },
]

history_cards_html = []
for card in history_cards:
    df_years = history_csvs(card["path"])
    years = df_years["Year"].tolist()
    years_sorted = [str(y) for y in sorted({int(y) for y in years if y is not None})]
    year_list = " ".join(f"<span class=\"wm-year-pill\">{y}</span>" for y in years_sorted)
    most_recent = years[-1] if years else "N/A"
    count = len(years)
    metric_html = (
        colored_metric(
            label=card["title"],
            value=f"{count}",
            val_color=PRIMARY,
            bg_color="white",
            border_color="#13294B",
        )
        + f"""<div class="wm-history-years">{year_list}</div></div></div>"""
    )
    card_class = "wm-card-wide" if card["title"] == "NCAA Tournament Appearances" else ""
    history_cards_html.append(
        f"""<div class="wm-history-item {card_class}">
          {metric_html}
        </div>"""
    )

st.markdown(
    f"""
    <section class="wm-card-grid">
      {''.join(history_cards_html)}
    </section>
    """,
    unsafe_allow_html=True,
)

def load_winning_table(path, columns):
    df = pd.read_csv(path, header=None)
    df.columns = columns
    if "Rank" in df.columns:
        df = df.head(10).copy()
        df["Rank"] = [str(i) for i in range(1, len(df) + 1)]
    return df

def render_winning_cards(df, columns, has_pct=False):
    rows_html = []
    def slugify(text):
        text = str(text).strip().lower()
        text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
        return text or "col"
    for _, row in df.iterrows():
        cells = []
        for col in columns:
            value = row.get(col, "")
            if pd.isna(value):
                value = ""
            if has_pct and col == "Win %":
                try:
                    value = f"{float(value) * 100:.1f}%"
                except (TypeError, ValueError):
                    value = ""
            extra_class = ""
            if col == "Rank":
                extra_class = " wm-line-rank"
            elif col in {"Wins", "Win %"}:
                extra_class = " wm-line-value"
            elif col == "Year":
                extra_class = " wm-line-year"
                value = f"<span class=\"wm-year-pill-dark\">{value}</span>" if value != "" else ""
            if col == "Rank":
                value = f"Rank {value}" if value != "" else ""
            cells.append(
                f"<span class=\"wm-inline-item wm-col-{slugify(col)}{extra_class}\">{value}</span>"
            )
        rows_html.append(f"<div class=\"wm-win-line\">{''.join(cells)}</div>")
    return f"<div class=\"wm-win-card-grid\">{''.join(rows_html)}</div>"

st.subheader("Winningest Seasons")
st.markdown("Top seasons by total wins and win percentage (overall and Big Ten).")

winning_tables = [
    {
        "title": "Winningest Seasons (Total Wins)",
        "path": "data/processed/mbb_history_csv/Winningest_Seasons_By_Total_Wins.csv",
        "columns": ["Rank", "Wins", "Year"],
        "has_pct": False,
    },
    {
        "title": "Winningest Seasons (Win %)",
        "path": "data/processed/mbb_history_csv/Winningest_Seasons_By_Win_Percentage.csv",
        "columns": ["Rank", "Win %", "Record", "Year"],
        "has_pct": True,
    },
    {
        "title": "Winningest Big Ten Seasons (Total Wins)",
        "path": "data/processed/mbb_history_csv/Winningest_Big_Ten_Seasons_By_Total_Wins.csv",
        "columns": ["Rank", "Wins", "Year"],
        "has_pct": False,
    },
    {
        "title": "Winningest Big Ten Seasons (Win %)",
        "path": "data/processed/mbb_history_csv/Winningest_Big_Ten_Seasons_By_Win_Percentage.csv",
        "columns": ["Rank", "Win %", "Record", "Year"],
        "has_pct": True,
    },
]

left_col, right_col = st.columns(2)
for idx, table in enumerate(winning_tables):
    target = left_col if idx % 2 == 0 else right_col
    with target:
        df_table = load_winning_table(table["path"], table["columns"])
        cards_html = render_winning_cards(df_table, table["columns"], has_pct=table["has_pct"])
        card_html = f"<div class=\"wm-table-card\"><h4>{table['title']}</h4>{cards_html}</div>"
        st.markdown(card_html, unsafe_allow_html=True)

divider(SECONDARY)

st.subheader("Datasets Dictionary")
image3 = image_to_data_uri("data/images/1979–80_Illinois_Fighting_Illini_men's_basketball_team.jpg")
player_stats_updated = latest_data_update_for("data/processed/player_stats/*.csv")
player_info_updated = latest_data_update_for("data/processed/player_list.json")
team_stats_updated = latest_data_update_for("data/processed/season_stats.csv")
program_history_updated = latest_data_update_for("data/processed/mbb_history_csv")
recruiting_geo_updated = latest_data_update_for("data/processed/recruiting_geography.csv")
st.markdown(f"""
<section class="wm-split">

  <!-- LEFT: CARDS -->
  <div>
    <div class="wm-card-grid">
      <div class="wm-card wm-dataset-card">
        <h4>Player Stats</h4>
        <span class="wm-update-pill">Updated {player_stats_updated}</span>
        <strong>{format_year_range(player_stats_min_year, player_stats_max_year)}</strong>
        <p>Individual full season stats for each player on a specific roster</p>
      </div>
      <div class="wm-card wm-dataset-card">
        <h4>Player Info</h4>
        <span class="wm-update-pill">Updated {player_info_updated}</span>
        <strong>{format_year_range(player_min_year, player_max_year)}</strong>
        <p>Info on any given player across their entire tenure at Illinois. Includes height, jersey number, hometown, etc.</p>
      </div>
      <div class="wm-card wm-dataset-card">
        <h4>Team Stats</h4>
        <span class="wm-update-pill">Updated {team_stats_updated}</span>
        <strong>{format_year_range(team_stats_min_year, team_stats_max_year)}</strong>
        <p>Statistics that correlate to the team as a whole, across an entire given season.</p>
      </div>
      <div class="wm-card wm-dataset-card">
        <h4>Program History</h4>
        <span class="wm-update-pill">Updated {program_history_updated}</span>
        <strong>{format_year_range(history_min_year, history_max_year)}</strong>
        <p>A range of awards, tournament appearances, and winning percentages throughout Illinois history.</p>
      </div>
    </div>
    <div style="display:flex; justify-content:center; margin-top:16px;">
      <div class="wm-card wm-dataset-card" style="max-width:320px; width:100%;">
        <h4>Recruiting Geography</h4>
        <span class="wm-update-pill">Updated {recruiting_geo_updated}</span>
        <strong>{format_year_range(player_min_year, player_max_year)}</strong>
        <p>Hometowns, geocodes, and state/country tags for every Illinois roster player.</p>
      </div>
    </div>
  </div>

  <!-- RIGHT: IMAGE -->
  <div class="wm-split-img">
    <img src="{image3}" alt="Illinois Basketball Court" />
    <p style="text-align:center; font-size:0.9rem; color:#6b6b6b;">
      The 1979-80 Illinois Men's Basketball Team
    </p>
  </div>

</section>
""", unsafe_allow_html=True)

divider(SECONDARY)

st.subheader("Explore More Pages!")
st.markdown("""
            There are multiple ways to dive into the statistics behind the **Illini Men's Basketball Team**. 
            Use the buttons below to travel to the corresponding page!
            """)
nan1, left, nan3, right, nan2 = st.columns([0.25, 2, 0.5, 2, 0.25])
with left:
    if st.button("Team Overviews", width="stretch"):
        st.switch_page("pages/2_Team_Overviews.py")
    st.markdown(f"""
            <p style="text-align:center; font-size:0.9rem; color:#6b6b6b;">
                Explore the statistics surrounding a specific season.
            </p>
           """, unsafe_allow_html=True)
with right:
    if st.button("Player Dashboards", width="stretch"):
        st.switch_page("pages/3_Player_Dashbords.py")
    st.markdown(f"""
            <p style="text-align:center; font-size:0.9rem; color:#6b6b6b;">
                Explore the information and statistics on each player whos ever been on the Illinois roster.
            </p>
           """, unsafe_allow_html=True)
