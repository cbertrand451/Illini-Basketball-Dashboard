import argparse
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlsplit
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


MIN_ROSTER_PLAYERS = 5


def _player_link(name: str, href: str) -> bool:
    """Only accept actual men's basketball bio links, never ad/navigation links."""
    if not isinstance(name, str) or not isinstance(href, str):
        return False
    parsed = urlsplit(href)
    return bool(
        name.strip()
        and " ".join(name.split()).casefold() != "skip ad"
        and parsed.scheme in {"http", "https"}
        and parsed.hostname in {"fightingillini.com", "www.fightingillini.com"}
        and re.fullmatch(r"/sports/mens-basketball/roster/[^/]+/\d+/?", parsed.path)
        and not parsed.fragment
    )


def _parse_roster(html: str) -> List[Tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    results = {}
    # The first table may be an advertisement. Search roster bio links in all
    # tables instead, and require the sport-specific profile URL in every layout.
    links = soup.select(".sidearm-roster-player-name a, table a[href]")
    for link in links:
        name = link.get_text(" ", strip=True)
        href = urljoin("https://fightingillini.com", link.get("href", ""))
        if not _player_link(name, href):
            continue
        if "," in name:
            last, first = name.split(",", 1)
            name = f"{first.strip()} {last.strip()}"
        results[name] = href
    return list(results.items())


def _fetch_roster(url: str, allow_missing: bool = False) -> List[Tuple[str, str]]:
    response = requests.get(url, timeout=30)
    if allow_missing and response.status_code == 404:
        return []
    response.raise_for_status()
    players = _parse_roster(response.text)
    if len(players) < MIN_ROSTER_PLAYERS:
        raise ValueError(
            f"Refusing roster from {url}: found only {len(players)} valid player "
            "bio links. The site may have changed its HTML or returned an ad/"
            "error page. Existing player data has not been replaced."
        )
    return players


def _read_player_index(output_path: str) -> Dict[str, List[Any]]:
    if not os.path.exists(output_path):
        return {}
    with open(output_path, encoding="utf-8") as handle:
        players = json.load(handle)
    if not isinstance(players, dict):
        raise ValueError(f"Invalid cached player index: {output_path}")
    for name, info in players.items():
        if (not isinstance(info, list) or len(info) < 2
                or not isinstance(info[1], list) or not _player_link(name, info[0])):
            raise ValueError(
                f"Invalid cached player entry {name!r} in {output_path}. "
                "Restore the last valid index from Git before rebuilding."
            )
    return players


def _write_player_index(output_path: str, players: Dict[str, List[Any]]) -> None:
    """Validate before writing; keep a backup and atomically replace the index."""
    existing = _read_player_index(output_path)
    missing = existing.keys() - players.keys()
    if not players or missing:
        raise ValueError("Refusing to overwrite the index with empty or incomplete player data")
    for name, info in players.items():
        if not _player_link(name, info[0]):
            raise ValueError(f"Refusing invalid player entry: {name!r}")
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(players, handle, ensure_ascii=False, indent=2)
        if path.exists():
            shutil.copy2(path, str(path) + ".bak")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def scrape_rosters(output_path: str = None, verbose: bool = False) -> Dict[str, List[Any]]:
    """Fetch the current roster; optionally save without dropping cached players."""
    url = "https://fightingillini.com/sports/mens-basketball/roster"
    _log(f"Scraping roster page: {url}", verbose)
    roster = _fetch_roster(url)
    players = _read_player_index(output_path) if output_path is not None else {}
    for name, href in roster:
        if name in players:
            players[name][0] = href
        else:
            players[name] = [href, [], _safe_filename(name) + ".json"]
    if output_path is not None:
        _write_player_index(output_path, players)
    return players


def scrape_season_player_index(season: str, verbose: bool = False) -> List[Tuple[str, str]]:
    """Read a season roster; reject unrecognized HTML instead of scraping ads."""
    url = f"https://fightingillini.com/sports/mens-basketball/roster/{season}"
    _log(f"Scraping season roster: {season}", verbose)
    return _fetch_roster(url, allow_missing=True)


def build_player_index(
    output_path: str,
    start_year: int,
    end_year: int,
    verbose: bool = False,
) -> Dict[str, List[Any]]:
    """Merge validated rosters into the cached index and save only on success.

    Unavailable historical seasons (404) retain their downloaded entries. Other
    HTTP failures and suspicious/empty HTML abort before the index is written.
    """
    if start_year >= end_year:
        raise ValueError("start_year must be less than end_year")
    players = _read_player_index(output_path)
    current = scrape_rosters(verbose=verbose)
    for season in _season_list(start_year, end_year):
        roster = scrape_season_player_index(season, verbose=verbose)
        if not roster:
            print(f"Warning: roster {season} unavailable (404); retaining cached entries.")
        for name, url in roster:
            if name not in players:
                players[name] = [url, [], _safe_filename(name) + ".json"]
            if season not in players[name][1]:
                players[name][1].append(season)
            players[name][0] = url
    # Prefer current bio URLs over links from earlier seasons.
    for name, info in current.items():
        if name not in players:
            players[name] = info
        else:
            players[name][0] = info[0]
    for name, info in players.items():
        info[1] = sorted(set(info[1]), key=_season_sort_key)
        if len(info) < 3:
            info.append(_safe_filename(name) + ".json")
    players = dict(sorted(players.items(), key=lambda item: (
        _season_sort_key(item[1][1][-1])[0] if item[1][1] else 9999, item[0]
    )))
    _write_player_index(output_path, players)
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
