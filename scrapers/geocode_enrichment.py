import argparse
import json
import os
import re
from typing import Any, Dict, List, Optional

try:
    from geopy.geocoders import Nominatim
except Exception:
    Nominatim = None


def _log(message: str, verbose: bool) -> None:
    if verbose:
        print(message)


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


def _load_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_json(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def enrich_player_geocodes(players_dir: str, verbose: bool = False) -> List[str]:
    """Geocode hometowns for existing player JSON files."""
    if Nominatim is None:
        _log("Geocode disabled: geopy not available.", verbose)
        return []

    _log(f"Starting geocode enrichment: {players_dir}", verbose)
    geolocator = Nominatim(user_agent="illini-basketball-app-updater")

    written: List[str] = []
    for fname in os.listdir(players_dir):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(players_dir, fname)
        data = _load_json(path)
        if not data:
            continue
        header = data.get("header") or {}
        hometown = header.get("Hometown") or header.get("Hometown:")
        if not isinstance(hometown, str) or not hometown.strip():
            continue

        geocode = data.get("geocode") or {}
        if geocode.get("lat") is not None and geocode.get("lon") is not None:
            continue

        raw_hometown = hometown
        cleaned_hometown = _cleanup_hometown(hometown)
        lat = None
        lon = None
        try:
            loc = geolocator.geocode(cleaned_hometown)
            if not loc and cleaned_hometown != raw_hometown:
                loc = geolocator.geocode(raw_hometown)
            if loc:
                lat = loc.latitude
                lon = loc.longitude
        except Exception:
            _log(f"Geocode error for {data.get('name')}: '{raw_hometown}'", verbose)

        geocode = {
            "hometown": hometown,
            "lat": lat,
            "lon": lon,
            "is_illinois": bool("Ill." in hometown or "Illinois" in hometown),
        }
        data["geocode"] = geocode
        _write_json(path, data)
        written.append(path)
        _log(f"Updated geocode: {path}", verbose)

    _log(f"Geocode enrichment complete: {len(written)} files updated.", verbose)
    return written


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich player JSON files with geocoding.")
    parser.add_argument("--players-dir", default=os.path.join("data", "processed", "players"))
    parser.add_argument("--verbose", action="store_true", help="Force verbose logging.")
    parser.add_argument("--quiet", action="store_true", help="Disable logging.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if not os.path.exists(args.players_dir):
        _log(f"Missing players dir: {args.players_dir}", args.verbose)
        return
    if args.verbose:
        verbose = True
    elif args.quiet:
        verbose = False
    else:
        verbose = True
    enrich_player_geocodes(args.players_dir, verbose=verbose)


if __name__ == "__main__":
    main()
