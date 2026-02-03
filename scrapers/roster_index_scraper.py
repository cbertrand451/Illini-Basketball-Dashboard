import argparse
import json
import os
import re
from typing import Dict, Any, List, Tuple
from datetime import datetime

import requests
from bs4 import BeautifulSoup


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


def _absolute_url(href: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return f"https://fightingillini.com{href}"
    return href


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
        href = _absolute_url(name_tag.get("href", ""))
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
    _log("Starting roster index build.", verbose)
    players = scrape_rosters(output_path, verbose=verbose)
    _log(f"Found {len(players)} players on current roster.", verbose)

    for season in _season_list(start_year, end_year):
        season_players = scrape_season_player_index(season, verbose=verbose)
        if season_players:
            _log(f"Season {season}: {len(season_players)} players.", verbose)
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

    _log(f"Wrote player index: {output_path} ({len(players)} players).", verbose)
    return players


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the roster/player index.")
    parser.add_argument("--start-year", type=int, default=1944)
    parser.add_argument("--end-year", type=int, default=None)
    parser.add_argument("--output-path", default=os.path.join(DATA_DIR, "player_list.json"))
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
    build_player_index(
        output_path=args.output_path,
        start_year=args.start_year,
        end_year=end_year,
        verbose=verbose,
    )


if __name__ == "__main__":
    main()
