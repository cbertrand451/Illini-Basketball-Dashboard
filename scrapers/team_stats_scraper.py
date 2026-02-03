import argparse
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

import pandas as pd
import requests
from bs4 import BeautifulSoup


DATA_DIR = os.path.join("data", "processed")
SEASON_ROLLOVER_MONTH = 5
SEASON_ROLLOVER_DAY = 1


def _log(message: str, verbose: bool) -> None:
    if verbose:
        print(message)


def _season_list(start_year: int, end_year: int) -> List[str]:
    seasons = []
    for i in range(start_year, end_year):
        next_year_short = str((i + 1) % 100).zfill(2)
        seasons.append(f"{i}-{next_year_short}")
    return seasons


def _default_end_year() -> int:
    now = datetime.now()
    if (now.month, now.day) >= (SEASON_ROLLOVER_MONTH, SEASON_ROLLOVER_DAY):
        return now.year + 1
    return now.year


def _safe_filename(name: str) -> str:
    name_clean = re.sub(r"[^A-Za-z0-9_\-]", "_", name.strip())
    name_clean = re.sub(r"_+", "_", name_clean).strip("_")
    return name_clean or "unknown"


def add_season_start_year_column(
    df: pd.DataFrame,
    season_col: str = "Season",
    out_col: str = "Season Start Year",
) -> pd.DataFrame:
    """Add a numeric year column from the first year in a season string."""
    if df.empty or season_col not in df.columns:
        return df
    season_years = df[season_col].astype(str).str.extract(r"(\d{4})", expand=False)
    df[out_col] = pd.to_numeric(season_years, errors="coerce").astype("Int64")
    return df


def extract_stat_table(table, season: str) -> pd.DataFrame:
    """Parse team stats table from HTML to DataFrame."""
    rows = []
    for tr in table.find_all("tr")[1:]:
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue
        stat_span = tds[0].find("span", class_="hide-on-small-down")
        stat = stat_span.get_text(strip=True) if stat_span else tds[0].get_text(strip=True)
        illinois = tds[1].get_text(strip=True) if len(tds) > 1 else None
        opponents = tds[2].get_text(strip=True) if len(tds) > 2 else None
        rows.append({
            "Statistic": stat,
            "Illinois": illinois,
            "Opponents": opponents,
            "Season": season,
        })
    return pd.DataFrame(rows)


def extract_team_record(team_section) -> Tuple[Any, Any, Any, Any]:
    """Extract overall + conference wins/losses from the Team Stats header."""
    if team_section is None:
        return None, None, None, None
    header_text = team_section.find(string=re.compile(r"Team Stats", re.I))
    if not header_text:
        return None, None, None, None
    match = re.search(r"Team Stats\s*\(([^)]+)\)", str(header_text))
    if not match:
        return None, None, None, None
    parts = [part.strip() for part in match.group(1).split(",")]
    overall_record = parts[0] if parts else None
    conference_record = parts[1] if len(parts) > 1 else None

    def _split_record(record: Any) -> Tuple[Any, Any]:
        if not record:
            return None, None
        rec_match = re.search(r"(\d+)\s*-\s*(\d+)", str(record))
        if not rec_match:
            return None, None
        return int(rec_match.group(1)), int(rec_match.group(2))

    overall_wins, overall_losses = _split_record(overall_record)
    conference_wins, conference_losses = _split_record(conference_record)
    return overall_wins, overall_losses, conference_wins, conference_losses


def scrape_season_team_stats(season: str) -> Tuple[pd.DataFrame, Tuple[Any, Any, Any, Any]]:
    """Scrape season team stats from Fighting Illini site."""
    url = f"https://fightingillini.com/sports/mens-basketball/stats/{season}"
    res = requests.get(url)
    if res.status_code != 200:
        return pd.DataFrame(), (None, None, None, None)

    soup = BeautifulSoup(res.text, "html.parser")
    team_section = soup.find("section", id="team")
    team_table = team_section.find("table") if team_section else None
    team_stats = extract_stat_table(team_table, season) if team_table else pd.DataFrame()
    team_record = extract_team_record(team_section)

    return team_stats, team_record


def create_team_stats_df(
    df: pd.DataFrame,
    year: str,
    overall_wins: Any = None,
    overall_losses: Any = None,
    conference_wins: Any = None,
    conference_losses: Any = None,
) -> pd.DataFrame:
    """Normalize the team stats to a wide format for the season CSV."""
    df_melted = df.melt(
        id_vars=["Season", "Statistic"],
        value_vars=["Illinois", "Opponents"],
        var_name="Team",
        value_name="Value",
    )

    df_melted.loc[12, "Statistic"] = "Total Rebounds"
    df_melted.loc[13, "Statistic"] = "Rebounds Per Game"
    df_melted.loc[14, "Statistic"] = "Rebound Margin"
    df_melted.loc[15, "Statistic"] = "Total Assists"
    df_melted.loc[16, "Statistic"] = "Assists Per Game"
    df_melted.loc[17, "Statistic"] = "Total Turnovers"
    df_melted.loc[18, "Statistic"] = "Turnovers Per Game"
    df_melted.loc[19, "Statistic"] = "Turnovers Margin"
    df_melted.loc[22, "Statistic"] = "Total Steals"
    df_melted.loc[23, "Statistic"] = "Steals Per Game"
    df_melted.loc[24, "Statistic"] = "Total Blocks"
    df_melted.loc[25, "Statistic"] = "Blocks Per Game"
    df_melted.loc[26, "Statistic"] = "Total Attendance"
    df_melted.loc[27, "Statistic"] = "Attendance Per Game"
    df_melted.loc[40, "Statistic"] = "Total Rebounds"
    df_melted.loc[41, "Statistic"] = "Rebounds Per Game"
    df_melted.loc[42, "Statistic"] = "Rebound Margin"
    df_melted.loc[43, "Statistic"] = "Total Assists"
    df_melted.loc[44, "Statistic"] = "Assists Per Game"
    df_melted.loc[45, "Statistic"] = "Total Turnovers"
    df_melted.loc[46, "Statistic"] = "Turnovers Per Game"
    df_melted.loc[47, "Statistic"] = "Turnovers Margin"
    df_melted.loc[50, "Statistic"] = "Total Steals"
    df_melted.loc[51, "Statistic"] = "Steals Per Game"
    df_melted.loc[52, "Statistic"] = "Total Blocks"
    df_melted.loc[53, "Statistic"] = "Blocks Per Game"
    df_melted.loc[54, "Statistic"] = "Total Attendance"
    df_melted.loc[55, "Statistic"] = "Attendance Per Game"

    df_wide = df_melted.pivot(index="Team", columns="Statistic", values="Value")
    df_wide["Season"] = year
    df_wide["Overall Wins"] = pd.NA
    df_wide["Overall Losses"] = pd.NA
    df_wide["Conference Wins"] = pd.NA
    df_wide["Conference Losses"] = pd.NA

    if overall_wins is not None:
        df_wide.loc["Illinois", "Overall Wins"] = overall_wins
    if overall_losses is not None:
        df_wide.loc["Illinois", "Overall Losses"] = overall_losses
    if conference_wins is not None:
        df_wide.loc["Illinois", "Conference Wins"] = conference_wins
    if conference_losses is not None:
        df_wide.loc["Illinois", "Conference Losses"] = conference_losses

    df_wide = df_wide[[
        "Total Points",
        "Points Per Game",
        "Scoring Margin",
        "FG: Made-Attempted",
        "FG: Percentage",
        "FG: Per Game",
        "3PT: Made-Attempted",
        "3PT: Percentage",
        "3PT: Per Game",
        "FT: Made-Attempted",
        "FT: Percentage",
        "FT: Per Game",
        "Total Rebounds",
        "Rebounds Per Game",
        "Rebound Margin",
        "Total Assists",
        "Assists Per Game",
        "Total Turnovers",
        "Turnovers Per Game",
        "Turnovers Margin",
        "Assist/Turnover Ratio",
        "Points Off Turnovers",
        "Total Steals",
        "Steals Per Game",
        "Total Blocks",
        "Blocks Per Game",
        "Total Attendance",
        "Attendance Per Game",
        "Overall Wins",
        "Overall Losses",
        "Conference Wins",
        "Conference Losses",
        "Season",
    ]]
    return df_wide


def update_season_stats_csv(
    output_path: str,
    start_year: int,
    end_year: int,
    teams_dir: Optional[str] = None,
    verbose: bool = False,
) -> pd.DataFrame:
    """Scrape all seasons and write season_stats.csv."""
    _log("Starting team stats build.", verbose)
    season_dfs = []
    for season in _season_list(start_year, end_year):
        _log(f"Scraping season team stats: {season}", verbose)
        team_df, team_record = scrape_season_team_stats(season)
        if not team_df.empty:
            overall_wins, overall_losses, conference_wins, conference_losses = team_record
            fixed_team = create_team_stats_df(
                team_df,
                season,
                overall_wins=overall_wins,
                overall_losses=overall_losses,
                conference_wins=conference_wins,
                conference_losses=conference_losses,
            ).reset_index()
            season_dfs.append(fixed_team)
    if not season_dfs:
        _log("No season team stats found; nothing written.", verbose)
        return pd.DataFrame()
    df_seasons = pd.concat(season_dfs, ignore_index=True)
    df_seasons = add_season_start_year_column(df_seasons)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df_seasons.to_csv(output_path, index=False)
    _log(f"Wrote team stats CSV: {output_path} ({len(df_seasons)} rows).", verbose)
    if teams_dir:
        build_team_season_files(output_path, teams_dir, verbose=verbose)
    return df_seasons


def build_team_season_files(season_stats_csv: str, output_dir: str, verbose: bool = False) -> int:
    """Create per-season team JSON files from season_stats.csv."""
    if not os.path.exists(season_stats_csv):
        _log(f"Missing season stats CSV: {season_stats_csv}", verbose)
        return 0
    df = pd.read_csv(season_stats_csv)
    if df.empty or "Season" not in df.columns or "Team" not in df.columns:
        _log("Season stats CSV missing required columns; skipping team JSONs.", verbose)
        return 0

    os.makedirs(output_dir, exist_ok=True)
    seasons = sorted(df["Season"].dropna().unique().tolist())
    written = 0
    for season in seasons:
        _log(f"Writing team season file: {season}", verbose)
        slice_df = df[df["Season"] == season]
        payload: Dict[str, Any] = {"Season": season}
        for team_name in ["Illinois", "Opponents"]:
            tdf = slice_df[slice_df["Team"] == team_name].copy()
            if not tdf.empty:
                rec = tdf.iloc[0].to_dict()
                rec.pop("Team", None)
                payload[team_name] = rec
        out_path = os.path.join(output_dir, f"{_safe_filename(season)}.json")
        with open(out_path, "w", encoding="utf-8") as out:
            json.dump(payload, out, ensure_ascii=False, indent=2)
        written += 1
    _log(f"Wrote {written} team season files to {output_dir}.", verbose)
    return written


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build season team stats CSV.")
    parser.add_argument("--start-year", type=int, default=1944)
    parser.add_argument("--end-year", type=int, default=None)
    parser.add_argument("--output-path", default=os.path.join(DATA_DIR, "season_stats.csv"))
    parser.add_argument("--teams-dir", default=os.path.join(DATA_DIR, "teams"))
    parser.add_argument("--no-team-json", action="store_true", help="Skip per-season team JSONs.")
    parser.add_argument("--verbose", action="store_true", help="Force verbose logging.")
    parser.add_argument("--quiet", action="store_true", help="Disable logging.")
    return parser.parse_args()


def _resolve_end_year(arg_end_year: int) -> int:
    if arg_end_year is not None:
        return arg_end_year
    env_val = os.getenv("END_YEAR")
    if env_val and env_val.isdigit():
        return int(env_val)
    return _default_end_year()


def main() -> None:
    args = _parse_args()
    end_year = _resolve_end_year(args.end_year)
    if args.verbose:
        verbose = True
    elif args.quiet:
        verbose = False
    else:
        verbose = True
    teams_dir = None if args.no_team_json else args.teams_dir
    update_season_stats_csv(
        output_path=args.output_path,
        start_year=args.start_year,
        end_year=end_year,
        teams_dir=teams_dir,
        verbose=verbose,
    )


if __name__ == "__main__":
    main()
