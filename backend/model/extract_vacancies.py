"""
Extract company, description and date from vacancies_2026.parquet.

Use it from model.py:
    from extract_vacancies import load_vacancies
    for v in load_vacancies():               # default: vacancies_2026.parquet next to this file
        print(v["company"], v["date_posted"], v["description"][:80])

Or from the command line, to write a CSV that model.py can read directly:
    python extract_vacancies.py                        # -> vacancies_extracted.csv
    python extract_vacancies.py out.csv --sample 200   # small test file
    python extract_vacancies.py out.csv --limit 1000

Then:
    python model.py vacancies_extracted.csv out.jsonl --text-col description
"""
import argparse
import csv
import json
import sys
from datetime import date
from pathlib import Path
from typing import Iterator, Optional

import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
DEFAULT_PARQUET = HERE / "vacancies_2026.parquet"
COLUMNS = ["vacancy_id", "company", "description", "date_posted"]


def load_vacancies(
    path: Path = DEFAULT_PARQUET,
    limit: Optional[int] = None,
) -> Iterator[dict]:
    """Yield one dict per vacancy with keys: vacancy_id, company, description, date_posted.

    Only the needed columns are read from the parquet file, in batches, so the
    full 250 MB file is never loaded into memory at once.
    Missing values become "" for text fields and None for the date.
    """
    pf = pq.ParquetFile(str(path))
    yielded = 0
    for batch in pf.iter_batches(batch_size=10_000, columns=COLUMNS):
        data = batch.to_pydict()
        for i in range(batch.num_rows):
            if limit is not None and yielded >= limit:
                return
            posted = data["date_posted"][i]
            yield {
                "vacancy_id": data["vacancy_id"][i] or "",
                "company": data["company"][i] or "",
                "description": data["description"][i] or "",
                "date_posted": posted if isinstance(posted, date) else None,
            }
            yielded += 1


def write_csv(out_path: Path, rows: Iterator[dict]) -> int:
    """Write rows to CSV (model.py-compatible). Returns the number of rows written."""
    n = 0
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            r = dict(r)
            r["date_posted"] = r["date_posted"].isoformat() if r["date_posted"] else ""
            w.writerow(r)
            n += 1
    return n


def write_spine(out_path: Path, rows: list[dict]) -> int:
    """Write Contract 1 (spine_raw_jobs) rows as JSONL, for aggregate_skills.py."""
    n = 0
    with out_path.open("w", encoding="utf-8") as f:
        for r in rows:
            spine = {
                "job_id": r["vacancy_id"],
                "company_name": r["company"],
                "publication_date": r["date_posted"].isoformat() if r["date_posted"] else "",
            }
            f.write(json.dumps(spine, ensure_ascii=False) + "\n")
            n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("output", nargs="?", default=str(HERE / "vacancies_extracted.csv"))
    ap.add_argument("--parquet", default=str(DEFAULT_PARQUET))
    ap.add_argument("--limit", type=int, default=None, help="only the first N vacancies")
    ap.add_argument("--sample", type=int, default=None, help="alias for --limit (test runs)")
    ap.add_argument("--spine", default=None, help="also write the Contract 1 spine JSONL to this path")
    args = ap.parse_args()

    limit = args.limit if args.limit is not None else args.sample
    rows = list(load_vacancies(Path(args.parquet), limit=limit))
    n = write_csv(Path(args.output), rows)
    print(f"Wrote {n} vacancies to {args.output}", file=sys.stderr)
    if args.spine:
        m = write_spine(Path(args.spine), rows)
        print(f"Wrote {m} spine rows to {args.spine}", file=sys.stderr)


if __name__ == "__main__":
    main()
