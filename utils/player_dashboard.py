import math
from pathlib import Path

import pandas as pd
import streamlit as st


def format_stat_value(column: str, value) -> str:
    if pd.isna(value):
        return "-"
    if isinstance(value, (int, float)):
        if column.endswith("%"):
            return f"{value * 100:.1f}%"
        if "AVG" in column:
            return f"{value:.1f}"
        return f"{int(value)}" if float(value).is_integer() else f"{value:.1f}"
    return str(value)


def render_stats(df_row: pd.DataFrame) -> None:
    st.dataframe(df_row, use_container_width=True, hide_index=True)


def build_comparison_df(seasons_to_load: list[str], player_stats_dir: Path) -> pd.DataFrame:
    frames = []
    for season in seasons_to_load:
        season_path = player_stats_dir / f"{season}.csv"
        if not season_path.exists():
            continue
        frame = pd.read_csv(season_path)
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    return combined


def normalized_value(value, col_name: str, comparison_df: pd.DataFrame):
    if comparison_df.empty or col_name not in comparison_df.columns:
        return None
    series = pd.to_numeric(comparison_df[col_name], errors="coerce")
    min_value = series.min()
    max_value = series.max()
    if pd.isna(value) or pd.isna(min_value) or pd.isna(max_value) or max_value == min_value:
        return None
    return (value - min_value) / (max_value - min_value)


def arc_path(cx: float, cy: float, r: float, start_deg: float, end_deg: float) -> str:
    start_rad = math.radians(start_deg)
    end_rad = math.radians(end_deg)
    start_x = cx + r * math.cos(start_rad)
    start_y = cy + r * math.sin(start_rad)
    end_x = cx + r * math.cos(end_rad)
    end_y = cy + r * math.sin(end_rad)
    large_arc = 1 if abs(end_deg - start_deg) > 180 else 0
    return f"M {start_x:.2f} {start_y:.2f} A {r:.2f} {r:.2f} 0 {large_arc} 1 {end_x:.2f} {end_y:.2f}"
