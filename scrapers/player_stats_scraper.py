import argparse
import os
from typing import List
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


def extract_player_table(table, season: str) -> pd.DataFrame:
    """Parse player stats table from HTML to DataFrame."""
    thead_rows = table.find("thead").find_all("tr")
    row1 = thead_rows[0].find_all("th")
    row2 = thead_rows[1].find_all("th")

    headers = []
    group_labels = []
    for th in row1:
        colspan = int(th.get("colspan", 1))
        rowspan = int(th.get("rowspan", 1))
        label = th.get_text(strip=True)
        if rowspan == 2:
            headers.append(label)
        else:
            group_labels.extend([label] * colspan)

    for i, th in enumerate(row2):
        label = th.get_text(strip=True)
        if label in ["TOT", "AVG"]:
            headers.append(f"{group_labels[i]} {label}")
        else:
            headers.append(label)

    rows = []
    for tr in table.find("tbody").find_all("tr"):
        tds = tr.find_all("td")
        if not tds or len(tds) < 2:
            continue
        row_data = {}
        for i in range(min(len(headers), len(tds))):
            header = headers[i]
            cell = tds[i].get_text(strip=True)
            if header == "Player":
                name_tag = tds[i].find("a")
                raw_name = name_tag.get_text(strip=True) if name_tag else cell
                if "," in raw_name:
                    last, first = raw_name.split(",", 1)
                    cell = f"{first.strip()} {last.strip()}"
            row_data[header] = cell
        rows.append(row_data)
    df = pd.DataFrame(rows)
    if not df.empty:
        df["Season"] = season
    return df


def scrape_season_player_stats(season: str) -> pd.DataFrame:
    """Scrape player stats from Fighting Illini site for a season."""
    url = f"https://fightingillini.com/sports/mens-basketball/stats/{season}"
    res = requests.get(url)
    if res.status_code != 200:
        return pd.DataFrame()

    soup = BeautifulSoup(res.text, "html.parser")
    player_section = soup.find("section", id="individual-overall")
    player_table = player_section.find("table") if player_section else None
    return extract_player_table(player_table, season) if player_table else pd.DataFrame()


def fix_df(players_df: pd.DataFrame) -> pd.DataFrame:
    """Match the expected player stats schema used by the dashboard."""
    players_df_n = players_df.copy()

    players_df_n.loc[:, "Minutes TOT"] = players_df["PF"]
    players_df_n.loc[:, "Minutes AVG"] = players_df["AST"]
    players_df_n.loc[:, "FGM"] = players_df["TO"]
    players_df_n.loc[:, "FGA"] = players_df["STL"]
    players_df_n.loc[:, "FG%"] = players_df["BLK"]
    players_df_n.loc[:, "3PT"] = players_df["Bio Link"]
    players_df_n.loc[:, "3PTA"] = players_df["Minutes TOT"]
    players_df_n.loc[:, "3PT%"] = players_df["Minutes AVG"]
    players_df_n.loc[:, "FTM"] = players_df["FGM"]
    players_df_n.loc[:, "FTA"] = players_df["FGA"]
    players_df_n.loc[:, "FT%"] = players_df["FG%"]
    players_df_n.loc[:, "PTS"] = players_df["3PT"]
    players_df_n.loc[:, "Scoring AVG"] = players_df["3PTA"]
    players_df_n.loc[:, "OFF"] = players_df["3PT%"]
    players_df_n.loc[:, "DEF"] = players_df["FTM"]
    players_df_n.loc[:, "Rebounds TOT"] = players_df["FTA"]
    players_df_n.loc[:, "Rebounds AVG"] = players_df["FT%"]
    players_df_n.loc[:, "PF"] = players_df["PTS"]
    players_df_n.loc[:, "AST"] = players_df["Scoring AVG"]
    players_df_n.loc[:, "TO"] = players_df["OFF"]
    players_df_n.loc[:, "STL"] = players_df["DEF"]
    players_df_n.loc[:, "BLK"] = players_df["Rebounds TOT"]
    players_df_n.loc[:, "Bio Link"] = players_df["Rebounds AVG"]

    desired_order = [
        "#", "Player", "GP", "GS",
        "Minutes TOT", "Minutes AVG", "FGM", "FGA", "FG%",
        "3PT", "3PTA", "3PT%", "FTM", "FTA", "FT%",
        "PTS", "Scoring AVG", "OFF", "DEF",
        "Rebounds TOT", "Rebounds AVG", "PF", "AST", "TO", "STL", "BLK", "Bio Link",
    ]
    return players_df_n[desired_order]


def build_player_stats_files(
    output_dir: str,
    start_year: int,
    end_year: int,
    verbose: bool = False,
) -> List[str]:
    """Scrape per-season player stats and write CSVs."""
    _log("Starting player stats build.", verbose)
    os.makedirs(output_dir, exist_ok=True)
    written = []
    for season in _season_list(start_year, end_year):
        _log(f"Scraping player stats: {season}", verbose)
        player_stats = scrape_season_player_stats(season)
        if player_stats is None or player_stats.empty:
            continue
        fixed = fix_df(player_stats)
        if fixed is None or fixed.empty:
            continue
        fixed = fixed.drop(columns=["#", "Bio Link"], errors="ignore")
        out_path = os.path.join(output_dir, f"{season}.csv")
        fixed.to_csv(out_path, index=False)
        written.append(season)
        _log(f"Wrote player stats: {out_path} ({len(fixed)} rows).", verbose)
    if not written:
        _log("No player stats written.", verbose)
    return written


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build per-season player stats CSVs.")
    parser.add_argument("--start-year", type=int, default=1944)
    parser.add_argument("--end-year", type=int, default=None)
    parser.add_argument("--output-dir", default=os.path.join(DATA_DIR, "player_stats"))
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
    build_player_stats_files(
        output_dir=args.output_dir,
        start_year=args.start_year,
        end_year=end_year,
        verbose=verbose,
    )


if __name__ == "__main__":
    main()
