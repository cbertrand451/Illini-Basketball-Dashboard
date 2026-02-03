import json
import os
import re
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional

import requests
from bs4 import BeautifulSoup
import pandas as pd

try:
    from geopy.geocoders import Nominatim  
except Exception:
    Nominatim = None  


DATA_DIR = os.path.join("data", "processed")
SEASON_ROLLOVER_MONTH = 5
SEASON_ROLLOVER_DAY = 1


def _log(message: str, verbose: bool) -> None:
    if verbose:
        print(message)


def _safe_filename(name: str) -> str:
    name_clean = re.sub(r"[^A-Za-z0-9_\-]", "_", name.strip())
    name_clean = re.sub(r"_+", "_", name_clean).strip("_")
    return name_clean or "unknown"


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


def _season_sort_key(season: str) -> Tuple[int, str]:
    match = re.search(r"(\d{4})", str(season))
    if not match:
        return (9999, str(season))
    return (int(match.group(1)), str(season))


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


def _absolute_url(href: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return f"https://fightingillini.com{href}"
    return href


def _cleanup_hometown(value: str) -> str:
    cleaned = value.strip()
    if "/" in cleaned:
        cleaned = cleaned.split("/", 1)[0].strip()
    if "|" in cleaned:
        cleaned = cleaned.split("|", 1)[0].strip()
    cleaned = re.sub(r"\bIll\.\b", "Illinois", cleaned)
    cleaned = re.sub(r"\bIll\b", "Illinois", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _geocode_hometown(
    hometown: Optional[str],
    geolocator: Optional["Nominatim"],
    cache: Dict[str, Tuple[Optional[float], Optional[float]]],
    verbose: bool,
) -> Dict[str, Any]:
    if not isinstance(hometown, str) or not hometown.strip():
        return {"hometown": None, "lat": None, "lon": None, "is_illinois": False}

    is_illinois = bool("Ill." in hometown or "Illinois" in hometown)
    if geolocator is None:
        return {"hometown": hometown, "lat": None, "lon": None, "is_illinois": is_illinois}

    cleaned_hometown = _cleanup_hometown(hometown)
    cache_key = cleaned_hometown.lower()
    if cache_key in cache:
        lat, lon = cache[cache_key]
        return {"hometown": hometown, "lat": lat, "lon": lon, "is_illinois": is_illinois}

    lat = None
    lon = None
    try:
        loc = geolocator.geocode(cleaned_hometown)
        if not loc and cleaned_hometown != hometown:
            loc = geolocator.geocode(hometown)
        if loc:
            lat = loc.latitude
            lon = loc.longitude
    except Exception:
        _log(f"Geocode error for hometown: '{hometown}' into '{cleaned_hometown}", verbose)

    cache[cache_key] = (lat, lon)
    return {"hometown": hometown, "lat": lat, "lon": lon, "is_illinois": is_illinois}


def scrape_rosters(output_path: str, verbose: bool = False) -> Dict[str, List[Any]]:
    """
    Scrape roster list and write player_list.json.
    Returns a dict: {player_name: [url, [seasons...]]}
    """
    url = "https://fightingillini.com/sports/mens-basketball/roster"
    _log(f"Scraping roster page: {url}", verbose)
    res = requests.get(url)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    players: Dict[str, List[Any]] = {}
    roster_cards = soup.select("li.sidearm-roster-player")
    for card in roster_cards:
        name_tag = card.select_one(".sidearm-roster-player-name a")
        if not name_tag:
            continue
        name = name_tag.get_text(strip=True)
        href = name_tag.get("href", "")
        if href and href.startswith("/"):
            href = f"https://fightingillini.com{href}"

        # Attempt to read class/year as a proxy for season list if present.
        # This is a placeholder; the player seasons list is rebuilt below using stats scraping.
        players[name] = [href, []]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(players, f, ensure_ascii=False, indent=2)

    return players


def scrape_season_player_index(season: str, verbose: bool = False) -> List[Tuple[str, str]]:
    """Scrape player names + bio links from a season roster page."""
    url = f"https://fightingillini.com/sports/mens-basketball/roster/{season}"
    _log(f"Scraping season roster: {season}", verbose)
    res = requests.get(url)
    if res.status_code != 200:
        return []

    soup = BeautifulSoup(res.text, "html.parser")
    roster_cards = soup.select("li.sidearm-roster-player")
    results: List[Tuple[str, str]] = []
    if roster_cards:
        for card in roster_cards:
            name_tag = card.select_one(".sidearm-roster-player-name a")
            if not name_tag:
                continue
            name = name_tag.get_text(strip=True)
            href = _absolute_url(name_tag.get("href", ""))
            if name and href:
                results.append((name, href))
        return results

    # Fallback: some seasons may render roster in a table.
    table = soup.find("table")
    if not table:
        return []
    for tr in table.find("tbody").find_all("tr"):
        td = tr.find("td")
        if not td:
            continue
        a = td.find("a")
        if not a:
            continue
        raw_name = a.get_text(strip=True)
        href = _absolute_url(a.get("href", ""))
        if not raw_name or not href:
            continue
        if "," in raw_name:
            last, first = raw_name.split(",", 1)
            raw_name = f"{first.strip()} {last.strip()}"
        results.append((raw_name, href))
    return results


def build_player_index(
    output_path: str,
    start_year: int,
    end_year: int,
    verbose: bool = False,
) -> Dict[str, List[Any]]:
    """Build player index from current roster + all season roster pages."""
    players = scrape_rosters(output_path, verbose=verbose)

    for season in _season_list(start_year, end_year):
        season_players = scrape_season_player_index(season, verbose=verbose)
        for player_name, url in season_players:
            entry = players.get(player_name)
            if entry is None:
                players[player_name] = [url, [season]]
                continue
            if url and not entry[0]:
                entry[0] = url
            if season not in entry[1]:
                entry[1].append(season)

    for info in players.values():
        seasons = info[1] if isinstance(info, list) and len(info) > 1 else None
        if isinstance(seasons, list) and seasons:
            seasons = list(dict.fromkeys(seasons))
            info[1] = sorted(seasons, key=_season_sort_key)

    for player_name, info in players.items():
        if not isinstance(info, list):
            continue
        player_file = _safe_filename(player_name) + ".json"
        if len(info) < 3:
            info.append(player_file)
        else:
            info[2] = player_file

    def _player_sort_key(item: Tuple[str, List[Any]]) -> Tuple[int, str]:
        _, info = item
        if not isinstance(info, list) or len(info) < 2 or not info[1]:
            return (9999, item[0])
        return (_season_sort_key(info[1][-1])[0], item[0])

    players = dict(sorted(players.items(), key=_player_sort_key))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(players, f, ensure_ascii=False, indent=2)

    return players


def player_scrape_header_info(
    url: str,
    verbose: bool = False,
) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    """Scrape a player's roster page for header info and action photos."""
    try:
        res = requests.get(url)
        soup = BeautifulSoup(res.text, "html.parser")

        data: Dict[str, Any] = {}
        height_value = None
        weight_value = None
        action_photos: List[Dict[str, str]] = []

        jersey_tag = soup.find("span", class_="sidearm-roster-player-jersey-number")
        if jersey_tag:
            data["Jersey Number"] = jersey_tag.get_text(strip=True)

        first_name = soup.find("span", class_="sidearm-roster-player-first-name")
        last_name = soup.find("span", class_="sidearm-roster-player-last-name")
        if first_name and last_name:
            data["First Name"] = first_name.get_text(strip=True)
            data["Last Name"] = last_name.get_text(strip=True)
            data["Full Name"] = f"{data['First Name']} {data['Last Name']}"

        image_div = soup.find("div", class_="sidearm-roster-player-image")
        if image_div:
            img_tag = image_div.find("img")
            if img_tag and img_tag.get("src"):
                data["Image URL"] = img_tag["src"]

        social_links = soup.find_all("a", class_="sidearm-roster-player-social-link")
        for link in social_links:
            href = link.get("href", "")
            aria_label = link.get("aria-label", "")
            label = aria_label.split(" -", 1)[0].strip() if aria_label else ""
            if label:
                data[f"{label} URL"] = href

        for photo_div in soup.select("div.sidearm-roster-player-header-action-photo"):
            img_tag = photo_div.find("img")
            if not img_tag or not img_tag.get("src"):
                continue
            credit_div = photo_div.find_next_sibling(
                "div", class_="sidearm-roster-player-header-action-photos-credit"
            )
            if not credit_div and photo_div.parent:
                credit_div = photo_div.parent.find(
                    "div", class_="sidearm-roster-player-header-action-photos-credit"
                )
            credit = credit_div.get_text(strip=True) if credit_div else ""
            photo = {"url": img_tag["src"]}
            if credit:
                photo["credit"] = credit
            action_photos.append(photo)

        field_items = soup.select("div.sidearm-roster-player-fields li")
        for item in field_items:
            label_span = item.find("span", class_="sidearm-roster-player-field-label")
            value_span = label_span.find_next_sibling("span") if label_span else None
            if label_span and value_span:
                key = label_span.get_text(strip=True)
                value = value_span.get_text(strip=True)
                data[key] = value
                if key == "Height":
                    height_value = value
                elif key == "Weight":
                    weight_value = value
                elif key == "Ht./Wt." and value:
                    parts = [p.strip() for p in value.split("/") if p.strip()]
                    if parts:
                        height_value = parts[0]
                    if len(parts) > 1:
                        weight_value = parts[1]

        if height_value and "Height" not in data:
            data["Height"] = height_value
        if weight_value and "Weight" not in data:
            data["Weight"] = weight_value
        if height_value and "-" in height_value:
            feet_str, inches_str = height_value.split("-", 1)
            try:
                data["Height Inches"] = int(feet_str) * 12 + int(inches_str)
            except ValueError:
                _log(f"Invalid height format: '{height_value}'", verbose)

        return data, action_photos
    except Exception:
        return {}, []


def scrape_season_stats_w_players(
    season: str,
) -> Tuple[pd.DataFrame, pd.DataFrame, Tuple[Any, Any]]:
    """Scrape season team + player stats from Fighting Illini site."""
    url = f"https://fightingillini.com/sports/mens-basketball/stats/{season}"
    res = requests.get(url)
    if res.status_code != 200:
        return pd.DataFrame(), pd.DataFrame(), (None, None)

    soup = BeautifulSoup(res.text, "html.parser")

    team_section = soup.find("section", id="team")
    team_table = team_section.find("table") if team_section else None
    team_stats = extract_stat_table(team_table, season) if team_table else pd.DataFrame()
    team_record = extract_team_record(team_section)

    player_section = soup.find("section", id="individual-overall")
    player_table = player_section.find("table") if player_section else None
    player_stats = extract_player_table(player_table, season) if player_table else pd.DataFrame()

    return team_stats, player_stats, team_record


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
            "Season": season
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
        "Rebounds TOT", "Rebounds AVG", "PF", "AST", "TO", "STL", "BLK", "Bio Link"
    ]
    return players_df_n[desired_order]


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


def update_season_stats_csv(output_path: str, start_year: int, end_year: int, verbose: bool = False) -> pd.DataFrame:
    """Scrape all seasons and write season_stats.csv."""
    season_dfs = []
    for season in _season_list(start_year, end_year):
        _log(f"Scraping season stats: {season}", verbose)
        team_df, _, team_record = scrape_season_stats_w_players(season)
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
        return pd.DataFrame()
    df_seasons = pd.concat(season_dfs, ignore_index=True)
    df_seasons = add_season_start_year_column(df_seasons)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df_seasons.to_csv(output_path, index=False)
    return df_seasons


def update_mbb_history_csv_files(output_dir: str, verbose: bool = False) -> Dict[str, str]:
    """Scrape mens basketball history tables and write each to a CSV file."""
    url = "https://fightingillini.com/sports/2021/4/30/mens-basketball-history"
    _log(f"Fetching history tables page: {url}", verbose)
    res = requests.get(url)
    if res.status_code != 200:
        _log("Mens basketball history tables page not available; skipping CSV export.", verbose)
        return {}

    soup = BeautifulSoup(res.text, "html.parser")
    tables = soup.find_all("table", class_="release")
    if not tables:
        _log("No history tables found; skipping CSV export.", verbose)
        return {}

    os.makedirs(output_dir, exist_ok=True)
    outputs: Dict[str, str] = {}
    _log(f"Found {len(tables)} history tables.", verbose)
    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        header_cells = rows[0].find_all("th")
        if not header_cells:
            continue

        title = header_cells[0].get_text(strip=True).replace("\xa0", " ")
        if not title:
            continue

        raw_rows = []
        for tr in rows:
            cols = [cell.get_text(strip=True) for cell in tr.find_all(["td", "th"])]
            if cols:
                raw_rows.append(cols)

        if len(raw_rows) > 1:
            raw_rows = raw_rows[1:]

        df = pd.DataFrame(raw_rows)
        if df.shape[0] > 1:
            df.columns = df.iloc[0]
            df = df[1:].reset_index(drop=True)

        fname = f"{_safe_filename(title)}.csv"
        out_path = os.path.join(output_dir, fname)
        df.to_csv(out_path, index=False)
        outputs[title] = out_path
        _log(f"Wrote history CSV: {out_path}", verbose)

    return outputs


def build_player_metadata_files(
    player_list_path: str,
    output_dir: str,
    do_geocode: bool,
    verbose: bool = False,
) -> List[str]:
    """Create per-player JSON metadata files."""
    if not os.path.exists(player_list_path):
        return []
    with open(player_list_path, "r", encoding="utf-8") as f:
        player_list: Dict[str, List[Any]] = json.load(f)
    os.makedirs(output_dir, exist_ok=True)

    geolocator = None
    if do_geocode and Nominatim is not None:
        geolocator = Nominatim(user_agent="illini-basketball-app-updater")
    elif do_geocode and Nominatim is None:
        _log("Geocode disabled: geopy not available.", verbose)

    written: List[str] = []
    action_photo_urls: List[str] = []
    geocode_cache: Dict[str, Tuple[Optional[float], Optional[float]]] = {}
    player_items = list(player_list.items())
    total_players = len(player_items)
    for idx, (player_name, info) in enumerate(player_items, start=1):
        if not isinstance(info, list) or len(info) < 2:
            continue
        _log(f"[{idx}/{total_players}] Building player metadata: {player_name}", verbose)
        url = info[0]
        seasons = info[1]
        player_file = info[2] if len(info) > 2 and isinstance(info[2], str) else None
        header, action_photos = player_scrape_header_info(url, verbose=verbose)
        header = header or {}
        action_photos = action_photos or []
        for photo in action_photos:
            url_value = photo.get("url")
            if url_value:
                action_photo_urls.append(url_value)

        geocode = _geocode_hometown(
            header.get("Hometown") or header.get("Hometown:"),
            geolocator,
            geocode_cache,
            verbose,
        )

        data = {
            "name": player_name,
            "url": url,
            "seasons": seasons,
            "header": header,
            "action photos": action_photos,
            "geocode": geocode,
        }

        fname = player_file or (_safe_filename(player_name) + ".json")
        fpath = os.path.join(output_dir, fname)
        with open(fpath, "w", encoding="utf-8") as out:
            json.dump(data, out, ensure_ascii=False, indent=2)
        written.append(fpath)

    images_dir = os.path.join("data", "images")
    os.makedirs(images_dir, exist_ok=True)
    action_photos_path = os.path.join(images_dir, "action_photos.json")
    with open(action_photos_path, "w", encoding="utf-8") as out:
        json.dump(sorted(set(action_photo_urls)), out, ensure_ascii=False, indent=2)
    _log(f"Wrote action photo index: {action_photos_path}.", verbose)

    return written


def build_team_season_files(season_stats_csv: str, output_dir: str, verbose: bool = False) -> int:
    """Create per-season team JSON files from season_stats.csv."""
    if not os.path.exists(season_stats_csv):
        return 0
    df = pd.read_csv(season_stats_csv)
    if df.empty or "Season" not in df.columns or "Team" not in df.columns:
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
    return written


def build_player_stats_files(
    output_dir: str,
    start_year: int,
    end_year: int,
    verbose: bool = False,
) -> List[str]:
    """Scrape per-season player stats and write CSVs."""
    os.makedirs(output_dir, exist_ok=True)
    written = []
    for season in _season_list(start_year, end_year):
        _log(f"Scraping player stats: {season}", verbose)
        _, player_stats, _ = scrape_season_stats_w_players(season)
        if player_stats is None or player_stats.empty:
            continue
        fixed = fix_df(player_stats)
        if fixed is None or fixed.empty:
            continue
        fixed = fixed.drop(columns=["#", "Bio Link"], errors="ignore")
        out_path = os.path.join(output_dir, f"{season}.csv")
        fixed.to_csv(out_path, index=False)
        written.append(season)
    return written


def build_all(
    start_year: int = 1944,
    end_year: Optional[int] = None,
    do_geocode: bool = True,
    verbose: bool = False,
):
    """Run the full build and return a summary dict."""
    os.makedirs(DATA_DIR, exist_ok=True)
    if end_year is None:
        end_year = _default_end_year()

    _log("Starting full build.", verbose)
    player_index = build_player_index(
        output_path=os.path.join(DATA_DIR, "player_list.json"),
        start_year=start_year,
        end_year=end_year,
        verbose=verbose,
    )
    season_stats = update_season_stats_csv(
        output_path=os.path.join(DATA_DIR, "season_stats.csv"),
        start_year=start_year,
        end_year=end_year,
        verbose=verbose,
    )
    history_csvs = update_mbb_history_csv_files(
        os.path.join(DATA_DIR, "mbb_history_csv"),
        verbose=verbose,
    )
    player_meta_files = build_player_metadata_files(
        player_list_path=os.path.join(DATA_DIR, "player_list.json"),
        output_dir=os.path.join(DATA_DIR, "players"),
        do_geocode=do_geocode,
        verbose=verbose,
    )
    geocode_enriched = 0
    if do_geocode:
        try:
            from geocode_enrichment import enrich_player_geocodes
        except Exception:
            enrich_player_geocodes = None
        if enrich_player_geocodes:
            geocode_enriched = len(
                enrich_player_geocodes(os.path.join(DATA_DIR, "players"), verbose=verbose)
            )
    team_season_files = build_team_season_files(
        season_stats_csv=os.path.join(DATA_DIR, "season_stats.csv"),
        output_dir=os.path.join(DATA_DIR, "teams"),
        verbose=verbose,
    )
    player_stats_files = build_player_stats_files(
        output_dir=os.path.join(DATA_DIR, "player_stats"),
        start_year=start_year,
        end_year=end_year,
        verbose=verbose,
    )

    return {
        "player_index_count": 0 if not player_index else len(player_index),
        "season_stats_rows": 0 if season_stats is None else len(season_stats),
        "history_csv_files": 0 if not history_csvs else len(history_csvs),
        "player_meta_files": len(player_meta_files),
        "geocode_enriched_files": geocode_enriched,
        "team_season_files": team_season_files,
        "player_stats_seasons": len(player_stats_files),
    }


if __name__ == "__main__":
    summary = build_all(verbose=True)
    print("Build complete.")
    for key, value in summary.items():
        print(f"- {key}: {value}")
