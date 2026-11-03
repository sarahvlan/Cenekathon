#!/usr/bin/env python3
"""Slice 3 — Skill-tijdlijn per specifiek peer-bedrijf na de match (DuckDB).

Logica:
  1. Slice 2 levert gelijkaardige OUDE vacatures, elk met een company en publicatiedatum.
     Elke (bedrijf, match-jaar) is een startpunt.
  2. Per bedrijf volgen we de vacatures van DAT bedrijf in de jaren ná het match-jaar
     (Slice 1, enkel succesvolle peers indien de kolom bestaat, het doelbedrijf is uitgesloten).
  3. Per bedrijf en per opeenvolgend jaar na de match (1_jaar_na_match, 2_jaar_na_match, ...)
     berekenen we per skill het aandeel vacatures dat die skill vraagt.

  Een vacature van het bedrijf in jaar Y telt voor elk match-jaar A < Y, in de bucket
  (Y - A). Binnen één bucket telt elke vacature dus maximaal één keer.

Installatie:
    pip install duckdb

Gebruik:
    python skill_gap.py --similar slice2_similar.parquet --vacancies slice1_spine/ --out skill_tijdlijn.json

Invoer:
  --similar    Slice 2-output: parquet/csv/json met de kolommen
               company_clean, is_target_company, publication_date
  --vacancies  Slice 1-output: een parquet-bestand, of een map met parquet-bestanden
               (kolommen volgens Contract 1: job_id, company_name, publication_date,
               job_title, description_text, optioneel is_successful_growth_peer)

Uitvoer (JSON):
  {
    "<bedrijf>": {
      "1_jaar_na_match": {"<skill>": 0.25, ...},
      "2_jaar_na_match": {"<skill>": 0.45, ...}
    },
    ...
  }
  Percentages zijn fracties tussen 0 en 1. Aantallen en match-jaren staan in "meta".
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import duckdb

# --- Kolomnamen (pas aan als ze anders heten) --------------------------------
SIMILAR_COMPANY_COL = "company_clean"
SIMILAR_TARGET_COL = "is_target_company"
SIMILAR_DATE_COL = "publication_date"

JOB_ID_COL = "job_id"
COMPANY_COL = "company_name"
DATE_COL = "publication_date"
TITLE_COL = "job_title"
TEXT_COLS = ["job_title", "description_text"]  # kolommen waaruit skills worden gehaald
SUCCESS_COL = "is_successful_growth_peer"

# --- Skills: naam -> regex op titel + omschrijving (lowercase) ---------------
SKILL_PATTERNS = {
    "AI Governance": r"ai governance|responsible ai|ai-governance",
    "Machine Learning": r"machine learning|\bml\b",
    "Python": r"\bpython\b",
    "SQL": r"\bsql\b",
    "Power BI": r"power ?bi",
    "Cloud": r"\bcloud\b|\baws\b|\bazure\b|\bgcp\b",
    "AML": r"\baml\b|witwassen|anti[- ]money laundering",
    "KYC": r"\bkyc\b|know your customer",
    "GDPR": r"\bgdpr\b|\bavg\b",
    "Risk Management": r"risk management|risicomanagement",
    "Stakeholder Management": r"stakeholder",
    "Agile": r"\bagile\b|\bscrum\b",
}


def lit(value: str) -> str:
    """Veilige SQL-stringliteral."""
    return "'" + value.replace("'", "''") + "'"


def rate(num: int | None, den: int | None) -> float | None:
    return round((num or 0) / den, 4) if den else None


def scan_expr(path: Path) -> str:
    p = lit(str(path.resolve()))
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return f"read_parquet({p})"
    if suffix == ".csv":
        return f"read_csv({p}, header = true)"
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return f"read_json_auto({p})"
    sys.exit(f"Onbekend formaat voor --similar: {path}")


def spine_files(path: Path) -> list[Path]:
    files = sorted(path.glob("*.parquet")) if path.is_dir() else [path]
    if not files or any(f.suffix.lower() != ".parquet" for f in files):
        sys.exit(f"--vacancies moet een parquet-bestand of een map met parquet-bestanden zijn: {path}")
    return files


def rows(con: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def build(similar_path: Path, vacancies_path: Path) -> tuple[dict, dict]:
    con = duckdb.connect()

    # 1. Match-punten: elk (bedrijf, match-jaar) uit Slice 2, doelbedrijf uitgesloten
    con.execute(f"""
        CREATE TABLE match_points AS
        SELECT DISTINCT lower(trim(CAST({SIMILAR_COMPANY_COL} AS VARCHAR))) AS company,
               trim(CAST({SIMILAR_COMPANY_COL} AS VARCHAR)) AS company_display,
               year(TRY_CAST({SIMILAR_DATE_COL} AS DATE)) AS match_jaar
        FROM {scan_expr(similar_path)}
        WHERE NOT coalesce(CAST({SIMILAR_TARGET_COL} AS BOOLEAN), false)
          AND year(TRY_CAST({SIMILAR_DATE_COL} AS DATE)) IS NOT NULL
          AND trim(CAST({SIMILAR_COMPANY_COL} AS VARCHAR)) <> ''
    """)
    if not rows(con, "SELECT 1 FROM match_points LIMIT 1"):
        sys.exit("Geen bruikbare match-punten in het Slice 2-bestand (company_clean en publication_date nodig).")
    display = {r["company"]: r["company_display"] for r in rows(con, """
        SELECT company, max(company_display) AS company_display FROM match_points GROUP BY ALL""")}
    match_years = defaultdict(list)
    for r in rows(con, "SELECT company, match_jaar FROM match_points ORDER BY 1, 2"):
        match_years[r["company"]].append(r["match_jaar"])

    # 2. Vacatures van die bedrijven (Slice 1), met tekst
    files = spine_files(vacancies_path)
    file_list = "[" + ", ".join(lit(str(f.resolve())) for f in files) + "]"
    cols = [d[0] for d in con.execute(
        f"SELECT * FROM read_parquet({file_list}, union_by_name = true) LIMIT 0").description]
    has_flag = SUCCESS_COL in cols
    if not has_flag:
        print(f"WAARSCHUWING: kolom '{SUCCESS_COL}' ontbreekt; alle vacatures van de bedrijven worden meegenomen",
              file=sys.stderr)
    success_filter = f"WHERE coalesce(v.{SUCCESS_COL}, false)" if has_flag else ""
    text_expr = "concat_ws(' ', " + ", ".join(
        f"coalesce(CAST(v.{c} AS VARCHAR), '')" for c in TEXT_COLS) + ")"

    con.execute(f"""
        CREATE TABLE jobs AS
        SELECT DISTINCT ON (job_id) job_id, company, cal_year, body
        FROM (
            SELECT CAST(v.{JOB_ID_COL} AS VARCHAR) AS job_id,
                   lower(trim(CAST(v.{COMPANY_COL} AS VARCHAR))) AS company,
                   year(TRY_CAST(v.{DATE_COL} AS DATE)) AS cal_year,
                   lower({text_expr}) AS body
            FROM read_parquet({file_list}, union_by_name = true) AS v
            JOIN (SELECT DISTINCT company FROM match_points) AS p
              ON lower(trim(CAST(v.{COMPANY_COL} AS VARCHAR))) = p.company
            {success_filter}
        ) AS x
        WHERE cal_year IS NOT NULL
    """)

    # 3. Tijdlijn per bedrijf: elke vacature na een match-jaar, in bucket (jaar - match-jaar)
    con.execute("""
        CREATE TABLE followups AS
        SELECT j.job_id, j.body, m.company, j.cal_year - m.match_jaar AS jaar_na_match
        FROM jobs AS j
        JOIN match_points AS m ON j.company = m.company AND j.cal_year > m.match_jaar
    """)

    con.execute("CREATE TABLE skill_patterns (skill_name VARCHAR, pattern VARCHAR)")
    con.executemany("INSERT INTO skill_patterns VALUES (?, ?)", list(SKILL_PATTERNS.items()))
    con.execute("""
        CREATE TABLE skill_hits AS
        SELECT DISTINCT f.job_id, f.company, f.jaar_na_match, sp.skill_name
        FROM followups AS f
        JOIN skill_patterns AS sp ON regexp_matches(f.body, sp.pattern)
    """)

    # 4. Aggregatie per bedrijf en per jaar na de match (niet gepoold over bedrijven)
    totals = {(r["company"], r["jaar_na_match"]): r["n"] for r in rows(con, """
        SELECT company, jaar_na_match, count(DISTINCT job_id) AS n
        FROM followups GROUP BY ALL""")}
    hits = {(r["company"], r["jaar_na_match"], r["skill_name"]): r["n"] for r in rows(con, """
        SELECT company, jaar_na_match, skill_name, count(DISTINCT job_id) AS n
        FROM skill_hits GROUP BY ALL""")}

    result: dict[str, dict] = {}
    for (company, jaar), n_total in sorted(totals.items(), key=lambda kv: (display[kv[0][0]], kv[0][1])):
        skills = {}
        for (c, j, skill), n_with in hits.items():
            if c == company and j == jaar:
                skills[skill] = rate(n_with, n_total)
        skills = dict(sorted(skills.items(), key=lambda kv: -kv[1]))
        result.setdefault(display[company], {})[f"{jaar}_jaar_na_match"] = skills

    # 5. Meta
    n_per_jaar = defaultdict(dict)
    for (company, jaar), n_total in totals.items():
        n_per_jaar[display[company]][f"{jaar}_jaar_na_match"] = n_total
    without = sorted(display[c] for c in match_years if not any(k[0] == c for k in totals))

    print(f"Bedrijven met opvolging: {len(result)} | bedrijven zonder opvolging: {len(without)}")

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "vacancy_files": [f.name for f in files],
        "match_jaren_per_bedrijf": {display[c]: years for c, years in sorted(match_years.items())},
        "vacatures_per_bedrijf_per_jaar": {k: dict(v) for k, v in sorted(n_per_jaar.items())},
        "bedrijven_zonder_opvolging": without,
        "successful_filter_applied": has_flag,
        "jaar_na_match_definitie": "1_jaar_na_match = vacatures in het jaar direct na het match-jaar",
        "percentage_definitie": "aantal vacatures van het bedrijf met de skill / alle vacatures van het bedrijf in dat jaar (0-1)",
    }
    return result, meta


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--similar", type=Path, required=True,
                    help="Slice 2-output: gelijkaardige oude vacatures (parquet/csv/json)")
    ap.add_argument("--vacancies", type=Path, required=True,
                    help="Slice 1-output: parquet-bestand of map met parquet-bestanden")
    ap.add_argument("--out", type=Path, default=Path("skill_tijdlijn.json"))
    args = ap.parse_args()

    if not args.similar.is_file():
        sys.exit(f"Slice 2-bestand bestaat niet: {args.similar}")
    if not args.vacancies.exists():
        sys.exit(f"Slice 1-bestand/map bestaat niet: {args.vacancies}")

    result, meta = build(args.similar, args.vacancies)
    payload = {**result, "meta": meta}
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Geschreven naar {args.out}")


if __name__ == "__main__":
    main()
