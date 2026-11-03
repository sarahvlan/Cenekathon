"""
Aggregate extracted skills per company per year.

Joins extraction output (from model.py) with the Slice 1 spine (Contract 1) on
job_id, keeps only the most important skills, and writes:

1. company-year JSON: for every (company, year), the % of that company's
   vacancies in that year that mention each skill.
2. vacancy JSON (optional): for every vacancy, the important skills it mentions.

"Most important" = the N skills that appear in the most vacancies across the
whole corpus (default N=20).

Usage:
    python aggregate_skills.py skills.jsonl spine.jsonl company_year.json \
        [--vacancy-out vacancy_skills.json] [--top 20]

Spine: .jsonl or .csv with job_id, company_name, publication_date (YYYY-MM-DD).
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Extraction categories that count as skills.
SKILL_CATEGORIES = [
    "hard_skills",
    "tools_and_technologies",
    "soft_skills",
    "certifications_and_licenses",
    "languages",
]


def norm_skill(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def read_records(path: Path):
    """Yield dicts from a .jsonl or .csv file."""
    if path.suffix == ".jsonl":
        with path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)
    else:
        with path.open(encoding="utf-8", newline="") as f:
            yield from csv.DictReader(f)


def load_spine(path: Path) -> dict:
    """job_id -> (company, year). Skips rows without a company or a valid date."""
    spine = {}
    for r in read_records(path):
        company = (r.get("company_name") or "").strip()
        year = (r.get("publication_date") or "").strip()[:4]
        if company and re.fullmatch(r"\d{4}", year):
            spine[str(r["job_id"])] = (company, year)
    return spine


def load_skills(path: Path):
    """Yield (job_id, set of normalized skills) from extraction output."""
    for rec in read_records(path):
        skills = set()
        for cat in SKILL_CATEGORIES:
            for s in rec.get("skills", {}).get(cat) or []:
                n = norm_skill(s)
                if n:
                    skills.add(n)
        yield str(rec["id"]), skills


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("skills", type=Path, help="extraction output JSONL from model.py")
    ap.add_argument("spine", type=Path, help="Contract 1 spine (.jsonl or .csv)")
    ap.add_argument("output", type=Path, help="company-year JSON to write")
    ap.add_argument("--vacancy-out", type=Path, default=None, help="optional per-vacancy JSON")
    ap.add_argument("--top", type=int, default=20, help="number of most important skills to keep")
    args = ap.parse_args()

    spine = load_spine(args.spine)
    joined = []  # (job_id, company, year, skills)
    unmatched = 0
    for job_id, skills in load_skills(args.skills):
        if job_id not in spine:
            unmatched += 1
            continue
        company, year = spine[job_id]
        joined.append((job_id, company, year, skills))
    if not joined:
        sys.exit("No vacancies matched between the skills file and the spine (check job_id values).")

    # Most important skills = most vacancies in the corpus
    corpus = Counter()
    for *_, skills in joined:
        corpus.update(skills)
    important = {s for s, _ in corpus.most_common(args.top)}

    # Company-year totals and per-skill hit counts
    totals = Counter()
    hits = defaultdict(Counter)
    for _, company, year, skills in joined:
        totals[(company, year)] += 1
        hits[(company, year)].update(skills & important)

    company_year = []
    for (company, year) in sorted(totals):
        total = totals[(company, year)]
        skill_rows = [
            {"skill": s, "postings_with_skill": n, "pct_of_postings": round(100 * n / total, 1)}
            for s, n in hits[(company, year)].items()
        ]
        skill_rows.sort(key=lambda x: (-x["pct_of_postings"], x["skill"]))
        company_year.append({"company": company, "year": year,
                             "total_postings": total, "skills": skill_rows})
    args.output.write_text(json.dumps(company_year, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.vacancy_out:
        per_vacancy = [
            {"job_id": job_id, "company": company, "year": year,
             "skills": sorted(skills & important)}
            for job_id, company, year, skills in joined
        ]
        args.vacancy_out.write_text(json.dumps(per_vacancy, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"vacancies: {len(joined)}, important skills: {len(important)}, "
          f"company-years: {len(totals)}, unmatched skill rows: {unmatched}", file=sys.stderr)


if __name__ == "__main__":
    main()
