import argparse
import os
import re
from typing import Dict

import pandas as pd
import requests
from bs4 import BeautifulSoup


DATA_DIR = os.path.join("data", "processed")


def _log(message: str, verbose: bool) -> None:
    if verbose:
        print(message)


def _safe_filename(name: str) -> str:
    name_clean = re.sub(r"[^A-Za-z0-9_\-]", "_", name.strip())
    name_clean = re.sub(r"_+", "_", name_clean).strip("_")
    return name_clean or "unknown"


def update_mbb_history_csv_files(output_dir: str, verbose: bool = False) -> Dict[str, str]:
    """Scrape mens basketball history tables and write each to a CSV file."""
    _log("Starting history tables export.", verbose)
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

    if not outputs:
        _log("No history CSVs written.", verbose)
    return outputs


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export mens basketball history tables to CSV.")
    parser.add_argument("--output-dir", default=os.path.join(DATA_DIR, "mbb_history_csv"))
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
    update_mbb_history_csv_files(args.output_dir, verbose=verbose)


if __name__ == "__main__":
    main()
