"""Geef alle bedrijfsnamen uit de ruwe vacatures als JSON, voor de suggestielijst in de UI.

Gebruikt dezelfde invoer als Slice 1 (vacancies_*.parquet in de repo-root). De telling
gebeurt direct met DuckDB, zodat dit script niet de hele Slice 1-pipeline (yfinance) laadt.

Uitvoer: [{"name": "KBC", "n_vacancies": 123}, ...], gesorteerd op aantal vacatures.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[2]


def raw_company_counts(files: list[Path]) -> list[tuple[str, int]]:
    """Aantal vacatures per ruwe bedrijfsnaam (zelfde query als slice1/vacancy_export)."""
    paths = ", ".join("'" + str(f).replace("'", "''") + "'" for f in files)
    con = duckdb.connect()
    try:
        return con.execute(
            f"SELECT company, COUNT(*) AS n FROM read_parquet([{paths}], union_by_name = true) "
            "WHERE company IS NOT NULL GROUP BY company"
        ).fetchall()
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input-dir", type=Path, default=REPO, help="map met vacancies_*.parquet")
    args = ap.parse_args()

    files = sorted(args.input_dir.glob("vacancies_*.parquet"))
    if not files:
        print(f"Geen vacancies_*.parquet in {args.input_dir}", file=sys.stderr)
        return 1

    # Dezelfde naam met andere spaties of hoofdletters telt als één bedrijf.
    totals: dict[str, int] = {}
    display: dict[str, str] = {}
    for name, n in raw_company_counts(files):
        key = str(name).strip().lower()
        if not key:
            continue
        totals[key] = totals.get(key, 0) + int(n)
        display.setdefault(key, str(name).strip())
    companies = [
        {"name": display[k], "n_vacancies": totals[k]}
        for k in sorted(totals, key=lambda k: (-totals[k], k))
    ]
    print(json.dumps(companies, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
