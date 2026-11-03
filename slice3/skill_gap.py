#!/usr/bin/env python3
"""Slice 3 — Skill-tijdlijn per succesvol peer-bedrijf na de Slice 2-match (DuckDB).

Logica:
  1. Slice 2 (backend/model/match_company.py) geeft per gelijkaardig bedrijf een jaar:
     matches_<doelbedrijf>.csv met rank, company, year, similarity, ...
     Elke (bedrijf, year) is een startpunt.
  2. Het bedrijf wordt gekoppeld aan Slice 1 (slice1_output/spine_raw_jobs.parquet).
     Enkel succesvolle peers (is_successful_growth_peer = true) tellen mee. De koppeling
     loopt via vacancy_id: Slice 2 gebruikt de ruwe bedrijfsnaam, Slice 1 de canonieke naam.
  3. Per peer volgen we de vacatures van DAT bedrijf in de jaren ná het match-jaar uit de
     Slice 1-spine. Een vacature in jaar Y telt voor elk match-jaar A < Y in de bucket Y - A.
  4. Skills komen uit dezelfde LLM-extractie als Slice 2 (backend/model/model.py). Resultaten
     staan in dezelfde cache (match_cache/skills.jsonl), dus eerder verwerkte vacatures worden
     niet opnieuw verwerkt.
  5. Per bedrijf en per jaar na de match (1_jaar_na_match, 2_jaar_na_match, ...) het aandeel
     vacatures dat een top-skill vraagt.

Installatie (zelfde omgeving als Slice 1 en Slice 2):
    pip install -r requirements-slice1.txt openai

Gebruik:
    # Ollama moet draaien voor nieuwe vacatures (zie backend/model/model.py)
    python slice3/skill_gap.py --matches backend/model/matches_kbc.csv

Invoer:
  --matches   Slice 2-output (matches_<bedrijf>.csv) met de kolommen company en year.
              Optioneel: rank (met --top-matches) en similarity.
  --raw-dir   Map met de ruwe vacatures vacancies_*.parquet die Slice 2 gebruikte
              (standaard backend/model). Nodig voor de koppeling vacancy_id -> bron.
  --spine     Slice 1-output (Contract 1), standaard slice1_output/spine_raw_jobs.parquet.
  --cache     Skill-cache van Slice 2, standaard backend/model/match_cache/skills.jsonl.

Uitvoer (JSON):
  {
    "<bedrijf>": {
      "1_jaar_na_match": {"<skill>": 0.25, ...},
      "2_jaar_na_match": {"<skill>": 0.45, ...}
    },
    ...,
    "meta": {...}
  }
  Percentages zijn fracties tussen 0 en 1.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[1]
MODEL_DIR = REPO / "backend" / "model"
sys.path.insert(0, str(MODEL_DIR))
from aggregate_skills import load_skills  # noqa: E402  (hergebruik Slice 2)
from extract_vacancies import write_csv  # noqa: E402  (hergebruik Slice 2)

DEFAULT_SPINE = REPO / "slice1_output" / "spine_raw_jobs.parquet"
DEFAULT_CACHE = MODEL_DIR / "match_cache" / "skills.jsonl"

# Kolomnamen Slice 1 (Contract 1) en ruwe vacatures (Slice 2)
SPINE_JOB_ID = "job_id"
SPINE_COMPANY = "company_name"
SPINE_DATE = "publication_date"
SPINE_TEXT = "description_text"
SPINE_SUCCESS = "is_successful_growth_peer"
RAW_JOB_ID = "vacancy_id"
RAW_COMPANY = "company"
RAW_TEXT = "description"


def lit(value: str) -> str:
    """Veilige SQL-stringliteral."""
    return "'" + value.replace("'", "''") + "'"


def list_sql(files: list[Path]) -> str:
    return "[" + ", ".join(lit(str(f.resolve())) for f in files) + "]"


def scan_expr(path: Path) -> str:
    suffix = path.suffix.lower()
    p = lit(str(path.resolve()))
    if suffix == ".parquet":
        return f"read_parquet({p})"
    if suffix == ".csv":
        return f"read_csv({p}, header = true)"
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return f"read_json_auto({p})"
    sys.exit(f"Onbekend formaat voor --matches: {path}")


def rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def columns_of(con: duckdb.DuckDBPyConnection, source_sql: str) -> set[str]:
    return {d[0] for d in con.execute(f"SELECT * FROM {source_sql} LIMIT 0").description}


def extract_skills(csv_path: Path, cache_path: Path, concurrency: int) -> None:
    """Draai Slice 2's model.py. Ids die al in de cache staan, slaat model.py zelf over."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, str(MODEL_DIR / "model.py"), str(csv_path), str(cache_path),
         "--id-col", RAW_JOB_ID, "--text-col", RAW_TEXT, "--concurrency", str(concurrency)],
        check=True,
    )


def build(matches: Path, raw_dir: Path, spine: Path, cache: Path,
          top_matches: int | None, top_skills: int, concurrency: int) -> tuple[dict, dict]:
    raw_files = sorted(raw_dir.glob("vacancies_*.parquet"))
    if not raw_files:
        sys.exit(f"Geen vacancies_*.parquet in {raw_dir} (gebruik --raw-dir).")
    if not spine.is_file():
        sys.exit(f"Slice 1-spine niet gevonden: {spine}. Draai eerst slice1_pipeline.py.")
    con = duckdb.connect()

    # 1. Slice 1-spine: enkel succesvolle peers, canonieke naam
    spine_sql = f"read_parquet({lit(str(spine.resolve()))})"
    spine_cols = columns_of(con, spine_sql)
    missing = {SPINE_JOB_ID, SPINE_COMPANY, SPINE_DATE, SPINE_TEXT, SPINE_SUCCESS} - spine_cols
    if missing:
        sys.exit(f"Slice 1-spine mist kolommen: {sorted(missing)}")
    con.execute(f"""
        CREATE TABLE spine AS
        SELECT CAST({SPINE_JOB_ID} AS VARCHAR) AS job_id,
               lower(trim({SPINE_COMPANY})) AS canon_key,
               trim({SPINE_COMPANY}) AS company_name,
               CAST({SPINE_DATE} AS DATE) AS pub_date,
               year(CAST({SPINE_DATE} AS DATE)) AS cal_year,
               {SPINE_TEXT} AS description_text
        FROM {spine_sql}
        WHERE coalesce({SPINE_SUCCESS}, false)
    """)

    # 2. Ruwe vacatures: vacancy_id -> ruwe bedrijfsnaam + bronbestand (zelfde id-vorm als Slice 2)
    con.execute(f"""
        CREATE TABLE raw AS
        SELECT DISTINCT ON (job_id) job_id, raw_key, src FROM (
            SELECT CAST({RAW_JOB_ID} AS VARCHAR) AS job_id,
                   lower(trim({RAW_COMPANY})) AS raw_key,
                   regexp_replace(filename, '^.*/|\\.parquet$', '', 'g') AS src
            FROM read_parquet({list_sql(raw_files)}, filename = true, union_by_name = true)
        )
    """)
    # Koppel ruwe naam -> canonieke naam via vacancy_id (alleen succesvolle peers)
    con.execute("""
        CREATE TABLE raw_map AS
        SELECT DISTINCT r.raw_key, s.canon_key, s.company_name
        FROM raw AS r JOIN spine AS s USING (job_id)
    """)

    # 3. Match-punten uit Slice 2: (succesvol peer, match-jaar)
    mcols = columns_of(con, scan_expr(matches))
    company_col = "company" if "company" in mcols else "company_clean"
    if "year" in mcols:
        year_expr = "CAST(x.year AS INTEGER)"
    elif "match_jaar" in mcols:
        year_expr = "CAST(x.match_jaar AS INTEGER)"
    elif "publication_date" in mcols:
        year_expr = "year(TRY_CAST(x.publication_date AS DATE))"
    else:
        sys.exit("Slice 2-bestand mist een kolom year (of match_jaar / publication_date).")
    rank_filter = ""
    if top_matches is not None:
        if "rank" in mcols:
            rank_filter = f"AND CAST(x.rank AS INTEGER) <= {int(top_matches)}"
        else:
            print("WAARSCHUWING: --top-matches genegeerd; geen rank-kolom in het Slice 2-bestand",
                  file=sys.stderr)
    con.execute(f"""
        CREATE TABLE match_points AS
        SELECT DISTINCT m.canon_key AS company, m.company_name AS company_display,
               {year_expr} AS match_jaar
        FROM {scan_expr(matches)} AS x
        JOIN raw_map AS m ON lower(trim(CAST(x.{company_col} AS VARCHAR))) = m.raw_key
        WHERE {year_expr} IS NOT NULL {rank_filter}
    """)
    if not rows(con, "SELECT 1 FROM match_points LIMIT 1"):
        sys.exit("Geen van de Slice 2-bedrijven is een succesvol peer in de Slice 1-spine "
                 "(controleer de bedrijfsnamen en --top-matches).")

    # 4. Vervolgvacatures: elke vacature van dat bedrijf ná het match-jaar
    con.execute("""
        CREATE TABLE followups AS
        SELECT s.job_id, s.canon_key AS company, s.company_name, s.pub_date, s.description_text,
               coalesce(r.src, 'spine') AS src,
               s.cal_year - m.match_jaar AS jaar_na_match
        FROM spine AS s
        JOIN match_points AS m ON s.canon_key = m.company AND s.cal_year > m.match_jaar
        LEFT JOIN raw AS r ON r.job_id = s.job_id
    """)
    fu = rows(con, "SELECT DISTINCT job_id, src, company, company_name, pub_date, description_text FROM followups")

    # 5. Skills: Slice 2-cache hergebruiken, ontbrekende vacatures extraheren met model.py
    fu_by_id = {f"{r['src']}:{r['job_id']}": r for r in fu}  # zelfde id-vorm als Slice 2
    to_csv = cache.parent / "slice3_followups.csv"
    cache.parent.mkdir(parents=True, exist_ok=True)
    write_csv(to_csv, [
        {"vacancy_id": cid, "company": r["company_name"], "description": r["description_text"],
         "date_posted": r["pub_date"]}
        for cid, r in fu_by_id.items()
    ])
    extract_skills(to_csv, cache, concurrency)

    all_skills = dict(load_skills(cache)) if cache.exists() else {}
    skills = {cid: all_skills[cid] for cid in fu_by_id if cid in all_skills}
    failed = [cid for cid in fu_by_id if cid not in skills]

    corpus = Counter()
    for sk in skills.values():
        corpus.update(sk)
    important = {s for s, _ in sorted(corpus.items(), key=lambda x: (-x[1], x[0]))[:top_skills]}

    # 6. Aggregatie per bedrijf en per jaar na de match
    # Een vacature telt per bucket maximaal één keer (set van cache-ids per bedrijf/bucket).
    bucket_ids: dict[tuple, set] = defaultdict(set)
    for r in rows(con, """
        SELECT DISTINCT f.src, f.job_id, f.company, f.jaar_na_match FROM followups AS f"""):
        cid = f"{r['src']}:{r['job_id']}"
        if cid in skills:
            bucket_ids[(r["company"], r["jaar_na_match"])].add(cid)

    display = {r["company"]: r["company_display"] for r in rows(
        con, "SELECT DISTINCT company, company_display FROM match_points")}
    result: dict[str, dict] = {}
    n_per_bucket: dict[str, dict] = defaultdict(dict)
    for (company, jaar) in sorted(bucket_ids, key=lambda k: (display[k[0]], k[1])):
        ids = bucket_ids[(company, jaar)]
        n_total = len(ids)
        hits = Counter()
        for cid in ids:
            hits.update(skills[cid] & important)
        pct = {s: round(n / n_total, 4) for s, n in hits.items()}
        pct = dict(sorted(pct.items(), key=lambda kv: (-kv[1], kv[0])))
        result.setdefault(display[company], {})[f"{jaar}_jaar_na_match"] = pct
        n_per_bucket[display[company]][f"{jaar}_jaar_na_match"] = n_total

    without = sorted(name for name in display.values() if name not in result)
    match_years = defaultdict(list)
    for r in rows(con, "SELECT company, company_display, match_jaar FROM match_points ORDER BY 1, 3"):
        match_years[r["company_display"]].append(r["match_jaar"])

    print(f"Bedrijven met opvolging: {len(result)} | zonder: {len(without)} | "
          f"vervolgvacatures met skills: {len(skills)} | zonder skills (fout): {len(failed)}")

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "matches_file": None,  # ingevuld door main()
        "spine": spine.name,
        "raw_files": [f.name for f in raw_files],
        "skill_cache": str(cache),
        "match_jaren_per_bedrijf": dict(sorted(match_years.items())),
        "vacatures_per_bedrijf_per_jaar": {k: dict(sorted(v.items())) for k, v in sorted(n_per_bucket.items())},
        "top_skills": sorted(important),
        "vervolgvacatures_zonder_skills": len(failed),
        "bedrijven_zonder_opvolging": without,
        "jaar_na_match_definitie": "1_jaar_na_match = vacatures in het jaar direct na het match-jaar",
        "percentage_definitie": "aantal vacatures van het bedrijf in die bucket met de skill / alle vacatures "
                                "van het bedrijf in die bucket (0-1)",
    }
    return result, meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--matches", type=Path, required=True, help="Slice 2-output: matches_<bedrijf>.csv")
    ap.add_argument("--raw-dir", type=Path, default=MODEL_DIR, help="map met ruwe vacancies_*.parquet")
    ap.add_argument("--spine", type=Path, default=DEFAULT_SPINE, help="Slice 1-output (Contract 1)")
    ap.add_argument("--cache", type=Path, default=DEFAULT_CACHE, help="skill-cache van Slice 2")
    ap.add_argument("--top-matches", type=int, default=None, help="alleen de N meest gelijkaardige (rank)")
    ap.add_argument("--top-skills", type=int, default=20, help="aantal meest voorkomende skills")
    ap.add_argument("--concurrency", type=int, default=8, help="parallelle LLM-verzoeken (model.py)")
    ap.add_argument("--out", type=Path, default=Path("skill_tijdlijn.json"))
    args = ap.parse_args()

    if not args.matches.is_file():
        sys.exit(f"Slice 2-bestand bestaat niet: {args.matches}")

    result, meta = build(args.matches, args.raw_dir, args.spine, args.cache,
                         args.top_matches, args.top_skills, args.concurrency)
    meta["matches_file"] = args.matches.name
    payload = {**result, "meta": meta}
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Geschreven naar {args.out}")


if __name__ == "__main__":
    main()
