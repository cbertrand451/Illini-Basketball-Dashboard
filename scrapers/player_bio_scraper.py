import argparse
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
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
) -> Tuple[Dict[str, Any], List[Dict[str, str]]]:
    """Scrape a player's roster page for header info and action photos."""
    res = requests.get(url, timeout=30)
    res.raise_for_status()
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

    if not data.get("Full Name"):
        raise ValueError(
            f"No recognizable player profile at {url}. The request may have "
            "returned an ad/error page, or the site layout has changed. "
            "Existing player profiles and photo index have not been replaced."
        )
    return data, action_photos


def build_player_bio_files(
    player_list_path: str,
    output_dir: str,
    do_geocode: bool = True,
    verbose: bool = False,
    images_dir: Optional[str] = None,
) -> List[str]:
    """Validate every download before writing any profiles or the photo index.

    A failed request or unrecognized HTML raises an error. Cached profile fields,
    photos and valid coordinates are retained when an update omits those fields.
    """
    with open(player_list_path, "r", encoding="utf-8") as handle:
        players = json.load(handle)
    if not isinstance(players, dict) or not players:
        raise ValueError("Refusing to build profiles from an empty/invalid player index")
    output = Path(output_dir)
    cached = {}
    geocode_cache = {}
    for path in output.glob("*.json"):
        data = _read_json(path, {})
        cached[path.name] = data
        geo = data.get("geocode") or {}
        if geo.get("hometown") and geo.get("lat") is not None and geo.get("lon") is not None:
            key = _cleanup_hometown(geo["hometown"]).casefold()
            geocode_cache[key] = (geo["lat"], geo["lon"])

    geolocator = None
    if do_geocode:
        if Nominatim is None:
            raise RuntimeError("Geocoding requested but geopy is unavailable")
        geolocator = Nominatim(user_agent="illini-basketball-app-updater")

    pending = {}
    for idx, (name, info) in enumerate(players.items(), start=1):
        if not isinstance(info, list) or len(info) < 2 or not isinstance(info[1], list):
            raise ValueError(f"Invalid player index entry: {name!r}")
        url, seasons = info[:2]
        filename = info[2] if len(info) > 2 else _safe_filename(name) + ".json"
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise ValueError(f"Invalid player filename: {filename!r}")
        previous = cached.get(filename, {})
        _log(f"[{idx}/{len(players)}] Downloading player bio: {name}", verbose)
        try:
            header, photos = player_scrape_header_info(url, verbose=verbose)
        except (requests.RequestException, ValueError) as exc:
            raise ValueError(
                f"Could not refresh {name} ({url}): {exc}. "
                "No player profiles or photo index were replaced."
            ) from exc
        if not header or not header.get("Full Name"):
            raise ValueError(f"Empty profile for {name}; no player profiles were replaced")
        merged_header = {**(previous.get("header") or {}),
                         **{key: value for key, value in header.items() if value not in (None, "")}}
        # A response with no gallery must not erase previously downloaded photos.
        merged_photos = {}
        for photo in [*(previous.get("action photos") or []), *(photos or [])]:
            photo = {"url": photo} if isinstance(photo, str) else photo
            if photo.get("url"):
                merged_photos[photo["url"]] = {**merged_photos.get(photo["url"], {}), **photo}
        hometown = merged_header.get("Hometown") or merged_header.get("Hometown:")
        old_geo = previous.get("geocode") or {}
        old_town = old_geo.get("hometown")
        same_town = bool(hometown and old_town and
                         _cleanup_hometown(hometown).casefold() == _cleanup_hometown(old_town).casefold())
        if same_town and old_geo.get("lat") is not None and old_geo.get("lon") is not None:
            geocode = old_geo
        elif hometown and _cleanup_hometown(hometown).casefold() in geocode_cache:
            lat, lon = geocode_cache[_cleanup_hometown(hometown).casefold()]
            geocode = {"hometown": hometown, "lat": lat, "lon": lon,
                       "is_illinois": "Ill." in hometown or "Illinois" in hometown}
        else:
            geocode = _geocode_hometown(hometown, geolocator, geocode_cache, verbose)
        pending[filename] = {
            **previous, "name": name, "url": url, "seasons": seasons,
            "header": merged_header, "action photos": list(merged_photos.values()),
            "geocode": geocode,
        }

    # No output is touched until all HTTP responses and profile HTML pass.
    # Keep photos belonging to players outside a custom/subset index as well.
    photos_path = Path(images_dir or os.path.join("data", "images")) / "action_photos.json"
    photo_urls = set(_read_json(photos_path, []))
    for profile in {**cached, **pending}.values():
        for photo in profile.get("action photos") or []:
            url = photo.get("url") if isinstance(photo, dict) else photo
            if url:
                photo_urls.add(url)
    written = []
    for filename, payload in pending.items():
        path = output / filename
        _write_json(path, payload)
        written.append(str(path))
    _write_json(photos_path, sorted(photo_urls))
    _log(f"Wrote {len(written)} player profiles and preserved the photo index.", verbose)
    return written


def _read_json(path: Path, default):
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, payload) -> None:
    """Serialize before replacing a file, retaining a local backup."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        if path.exists():
            shutil.copy2(path, str(path) + ".bak")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


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
