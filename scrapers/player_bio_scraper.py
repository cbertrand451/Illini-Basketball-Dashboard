import argparse
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

try:
    from geopy.geocoders import Nominatim
except Exception:
    Nominatim = None


DATA_DIR = os.path.join("data", "processed")


def _log(message: str, verbose: bool) -> None:
    if verbose:
        print(message)


def _safe_filename(name: str) -> str:
    name_clean = re.sub(r"[^A-Za-z0-9_\-]", "_", name.strip())
    name_clean = re.sub(r"_+", "_", name_clean).strip("_")
    return name_clean or "unknown"


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


def player_scrape_header_info(
    url: str,
    verbose: bool = False,
) -> (Dict[str, Any], List[Dict[str, str]]):
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


def build_player_bio_files(
    player_list_path: str,
    output_dir: str,
    do_geocode: bool = True,
    verbose: bool = False,
) -> List[str]:
    """Create per-player JSON bio files with geocoding."""
    _log("Starting player bio build.", verbose)
    if not os.path.exists(player_list_path):
        _log(f"Missing player list: {player_list_path}", verbose)
        return []
    with open(player_list_path, "r", encoding="utf-8") as f:
        player_list: Dict[str, List[Any]] = json.load(f)
    os.makedirs(output_dir, exist_ok=True)

    written: List[str] = []
    action_photo_urls: List[str] = []
    geolocator = None
    if do_geocode and Nominatim is not None:
        geolocator = Nominatim(user_agent="illini-basketball-app-updater")
    elif do_geocode and Nominatim is None:
        _log("Geocode disabled: geopy not available.", verbose)
    geocode_cache: Dict[str, Tuple[Optional[float], Optional[float]]] = {}
    player_items = list(player_list.items())
    total_players = len(player_items)
    for idx, (player_name, info) in enumerate(player_items, start=1):
        if not isinstance(info, list) or len(info) < 2:
            continue
        _log(f"[{idx}/{total_players}] Building player bio: {player_name}", verbose)
        url = info[0]
        seasons = info[1]
        player_file = info[2] if len(info) > 2 and isinstance(info[2], str) else None
        header, action_photos = player_scrape_header_info(url, verbose=verbose)
        header = header or {}
        action_photos = action_photos or []
        for photo in action_photos:
            url = photo.get("url")
            if url:
                action_photo_urls.append(url)

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

    _log(f"Wrote {len(written)} player bio files to {output_dir}.", verbose)
    return written


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build player bio/header JSON files.")
    parser.add_argument("--player-list", default=os.path.join(DATA_DIR, "player_list.json"))
    parser.add_argument("--output-dir", default=os.path.join(DATA_DIR, "players"))
    parser.add_argument("--no-geocode", action="store_true", help="Skip geocoding hometowns.")
    parser.add_argument("--verbose", action="store_true", help="Force verbose logging.")
    parser.add_argument("--quiet", action="store_true", help="Disable logging.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if args.verbose:
        verbose = True
    elif args.quiet:
        verbose = False
    else:
        verbose = True
    build_player_bio_files(
        player_list_path=args.player_list,
        output_dir=args.output_dir,
        do_geocode=not args.no_geocode,
        verbose=verbose,
    )


if __name__ == "__main__":
    main()
