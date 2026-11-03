"""
Rank older company-years by how closely their skill profile matches a target company's current vacancies.

For one target company (e.g. KBC):
  1. Takes its vacancies from the target year (default 2026) and extracts their skills.
  2. Takes vacancies of every OTHER company from the older parquet files (vacancies_*.parquet),
     capped per company-year, and extracts their skills.
  3. Builds a skill-percentage profile per company-year (top N skills across the corpus).
  4. Ranks company-years by cosine similarity to the target profile, highest first.

Outputs:
  matches_<company>.csv              rank, company, year, similarity, vacancies, shared_skills
  target_<company>_<year>.json       the target's vacancies with their important skills

Usage (one command, runs Slice 1 first):
    python match_company.py KBC --run-slice1 --target-symbol KBC.BR

Usage (Slice 1 already run; use its spine):
    python match_company.py KBC --spine ../../slice1_output/spine_raw_jobs.parquet

Usage (raw parquets, no Slice 1):
    python match_company.py KBC --candidate-parquets data/vacancies_2024.parquet data/vacancies_2025.parquet

Extraction results are cached in match_cache/skills.jsonl, so repeated runs only process new vacancies.
Note: the first 'per-group-cap' vacancies of each company-year are used (file order, not random).
"""
import argparse
import json
import math
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from aggregate_skills import load_skills
from extract_vacancies import load_vacancies, write_csv, write_spine

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"                       # vacancies_<year>.parquet files
OUTPUT_DIR = HERE / "output"                   # all results: matches CSV, target skill totals and vacancies
SLICE1_SCRIPT = HERE.parent.parent / "slice1_pipeline.py"
SLICE1_OUTPUT = HERE.parent.parent / "slice1_output"
SLICE1_SPINE = SLICE1_OUTPUT / "spine_raw_jobs.parquet"


def spine_rows(path: Path):
    """Read a Contract 1 spine (.parquet or .jsonl) and yield rows in load_vacancies() format."""
    if path.suffix == ".parquet":
        import pyarrow.parquet as pq
        records = pq.read_table(str(path)).to_pylist()
    else:
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    for r in records:
        posted = r.get("publication_date")
        if isinstance(posted, str) and posted:
            posted = date.fromisoformat(posted)
        yield {
            "vacancy_id": str(r["job_id"]),
            "company": r.get("company_name") or "",
            "description": r.get("description_text") or "",
            "date_posted": posted or None,
        }


def run_slice1(args):
    """Run Slice 1 (peer selection + vacancy export) for the target company."""
    cmd = [sys.executable, str(SLICE1_SCRIPT), "--target", args.company,
           "--input", *[str(p) for p in sorted(DATA_DIR.glob("vacancies_*.parquet"))]]
    if args.target_symbol:
        cmd += ["--target-symbol", args.target_symbol]
    cmd += ["--region-scope", args.region_scope]
    print("running Slice 1:", " ".join(cmd[:4]), "...", file=sys.stderr)
    subprocess.run(cmd, check=True)


def name_matches(name: str, query: str) -> bool:
    """'KBC' matches 'KBC', 'Kbc', 'KBC NV', 'KBC Bank & Verzekering', but not 'KBCX'."""
    n, q = name.strip().lower(), query.strip().lower()
    return n == q or n.startswith(q + " ")


def cosine(a: dict, b: dict) -> float:
    dot = sum(v * b.get(k, 0.0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


def safe_name(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("company", help="target company name, e.g. KBC")
    ap.add_argument("--spine", default=None,
                    help="Slice 1 spine (slice1_output/spine_raw_jobs.parquet). If set, target and peers come from it.")
    ap.add_argument("--run-slice1", action="store_true",
                    help="first run slice1_pipeline.py for this company, then use its spine")
    ap.add_argument("--target-symbol", default=None, help="Yahoo symbol for --run-slice1, e.g. KBC.BR")
    ap.add_argument("--region-scope", default="any", choices=["country", "europe", "any"],
                    help="peer region for --run-slice1. 'country' finds none for KBC (only Belgian peers); "
                         "'europe' finds none for StepStone (US-listed target). 'any' works for both. Default 'any'")
    ap.add_argument("--target-parquet", default=str(DATA_DIR / "vacancies_2026.parquet"),
                    help="used when --spine is not given")
    ap.add_argument("--target-year", type=int, default=2026)
    ap.add_argument("--candidate-parquets", nargs="*", default=None,
                    help="used when --spine is not given; default: data/vacancies_*.parquet except the target")
    ap.add_argument("--per-group-cap", type=int, default=30,
                    help="max vacancies taken per candidate company-year")
    ap.add_argument("--max-groups", type=int, default=None,
                    help="limit the number of candidate company-years (for quick tests)")
    ap.add_argument("--min-vacancies", type=int, default=3,
                    help="ignore candidate company-years with fewer vacancies than this")
    ap.add_argument("--top", type=int, default=20, help="number of most important skills")
    ap.add_argument("--concurrency", type=int, default=64)
    ap.add_argument("--cache-dir", default=str(HERE / "match_cache"))
    ap.add_argument("--out", default=None, help="output CSV (default output/matches_<company>.csv)")
    args = ap.parse_args()

    if args.run_slice1:
        run_slice1(args)
        args.spine = str(SLICE1_SPINE)

    cache = Path(args.cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    slug = safe_name(args.company)

    # Sources: Slice 1 spine (Contract 1) or the raw parquet files
    if args.spine:
        spine_list = list(spine_rows(Path(args.spine)))
        target_source = spine_list
        cand_sources = [("spine", spine_list)]
        origin = Path(args.spine).name
    else:
        target_path = Path(args.target_parquet)
        target_source = load_vacancies(target_path)
        if args.candidate_parquets is None:
            cand_paths = [p for p in sorted(DATA_DIR.glob("vacancies_*.parquet")) if p.resolve() != target_path.resolve()]
        else:
            cand_paths = [Path(p) for p in args.candidate_parquets]
        cand_sources = [(p.stem, load_vacancies(p)) for p in cand_paths]
        origin = target_path.name

    # 1. Target vacancies
    target_rows = [
        r for r in target_source
        if r["date_posted"] and r["date_posted"].year == args.target_year
        and r["description"].strip() and name_matches(r["company"], args.company)
    ]
    if not target_rows:
        sys.exit(f"No {args.target_year} vacancies found for '{args.company}' in {origin}.")
    names = sorted({r["company"] for r in target_rows})
    print(f"target: {len(target_rows)} vacancies under names {names}", file=sys.stderr)

    # 2. Candidate vacancies (other companies, older years), capped per company-year
    if not cand_sources:
        sys.exit("No candidate sources found.")

    groups = defaultdict(list)  # (company, year) -> [(source, row)]
    for src_name, rows_iter in cand_sources:
        for r in rows_iter:
            d = r["date_posted"]
            if not d or not r["description"].strip() or name_matches(r["company"], args.company):
                continue
            if d.year >= args.target_year:  # competitors only from years before the target year
                continue
            items = groups[(r["company"], d.year)]
            if len(items) < args.per_group_cap:
                items.append((src_name, r))
    groups = {k: v for k, v in groups.items() if len(v) >= args.min_vacancies}
    ordered = sorted(groups, key=lambda k: -len(groups[k]))
    if args.max_groups:
        ordered = ordered[: args.max_groups]
    print(f"candidates: {sum(len(groups[k]) for k in ordered)} vacancies in {len(ordered)} company-years",
          file=sys.stderr)
    if not ordered:
        sys.exit("No candidate company-years with enough vacancies. Check the candidate parquets/years.")

    skills_path = cache / "skills.jsonl"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 3a. Extract the target's own vacancies first, and write its skill totals right away
    target_tagged = [dict(r, vacancy_id=f"target:{r['vacancy_id']}") for r in target_rows]
    tgt_csv = cache / f"{slug}_target_selected.csv"
    write_csv(tgt_csv, target_tagged)
    subprocess.run(
        [sys.executable, str(HERE / "model.py"), str(tgt_csv), str(skills_path),
         "--id-col", "vacancy_id", "--text-col", "description", "--concurrency", str(args.concurrency)],
        check=True,
    )
    tgt_skills = {jid: sk for jid, sk in load_skills(skills_path) if jid.startswith("target:")}
    tgt_ids = [r["vacancy_id"] for r in target_tagged if r["vacancy_id"] in tgt_skills]
    if not tgt_ids:
        sys.exit("No target vacancies were extracted successfully.")
    tgt_counts = Counter(s for j in tgt_ids for s in tgt_skills[j])
    totals_out = OUTPUT_DIR / f"target_{slug}_{args.target_year}_skill_totals.json"
    totals = {
        "company": args.company,
        "year": str(args.target_year),
        "total_vacancies": len(tgt_ids),
        "skills": [
            {"skill": s, "vacancies_with_skill": c, "pct_of_vacancies": round(100.0 * c / len(tgt_ids), 1)}
            for s, c in sorted(tgt_counts.items(), key=lambda x: (-x[1], x[0]))
        ],
    }
    totals_out.write_text(json.dumps(totals, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"target skill totals written: {totals_out}", file=sys.stderr)

    # 3b. Extract the candidates (model.py skips the target ids that are already done)
    rows = list(target_tagged)
    for key in ordered:
        rows += [dict(r, vacancy_id=f"{src}:{r['vacancy_id']}") for src, r in groups[key]]
    sel_csv = cache / f"{slug}_selected.csv"
    sel_spine = cache / f"{slug}_spine.jsonl"
    write_csv(sel_csv, rows)
    write_spine(sel_spine, rows)
    subprocess.run(
        [sys.executable, str(HERE / "model.py"), str(sel_csv), str(skills_path),
         "--id-col", "vacancy_id", "--text-col", "description", "--concurrency", str(args.concurrency)],
        check=True,
    )

    # 4. Join skills with spine and build profiles
    spine = {}
    for line in sel_spine.read_text(encoding="utf-8").splitlines():
        s = json.loads(line)
        spine[s["job_id"]] = (s["company_name"], s["publication_date"][:4])
    skills = {jid: sk for jid, sk in load_skills(skills_path) if jid in spine}

    corpus = defaultdict(int)
    for sk in skills.values():
        for s in sk:
            corpus[s] += 1
    important = [s for s, _ in sorted(corpus.items(), key=lambda x: (-x[1], x[0]))[: args.top]]
    imp = set(important)

    target_ids = [f"target:{r['vacancy_id']}" for r in target_rows if f"target:{r['vacancy_id']}" in skills]
    if not target_ids:
        sys.exit("No target vacancies were extracted successfully.")
    n_t = len(target_ids)
    target_counts = {s: sum(1 for j in target_ids if s in skills[j] & imp) for s in important}
    target_profile = {s: 100.0 * c / n_t for s, c in target_counts.items() if c > 0}

    # target per-vacancy file
    target_out = OUTPUT_DIR / f"target_{slug}_{args.target_year}_vacancies.json"
    per_vac = [
        {"vacancy_id": r["vacancy_id"], "date_posted": r["date_posted"].isoformat(),
         "skills": sorted(skills[f"target:{r['vacancy_id']}"] & imp)}
        for r in target_rows if f"target:{r['vacancy_id']}" in skills
    ]
    target_out.write_text(json.dumps(per_vac, ensure_ascii=False, indent=2), encoding="utf-8")

    # candidate company-year profiles
    cy_ids = defaultdict(list)
    for jid, (company, year) in spine.items():
        if jid.startswith("target:") or jid not in skills:
            continue
        cy_ids[(company, year)].append(jid)

    results = []
    for (company, year), ids in cy_ids.items():
        if len(ids) < args.min_vacancies:
            continue
        prof = {s: 100.0 * sum(1 for j in ids if s in skills[j] & imp) / len(ids) for s in important}
        prof = {s: v for s, v in prof.items() if v > 0}
        sim = cosine(target_profile, prof)
        shared = sorted(
            (s for s in target_profile if s in prof),
            key=lambda s: -min(target_profile[s], prof[s]),
        )[:5]
        results.append((sim, company, year, len(ids), shared))

    results.sort(key=lambda x: -x[0])
    out = Path(args.out) if args.out else OUTPUT_DIR / f"matches_{slug}.csv"
    with out.open("w", encoding="utf-8", newline="") as f:
        f.write("rank,company,year,similarity,vacancies,shared_skills\n")
        for rank, (sim, company, year, n, shared) in enumerate(results, 1):
            cells = [str(rank), company, year, f"{sim:.3f}", str(n), "; ".join(shared)]
            f.write(",".join('"' + c.replace('"', '""') + '"' for c in cells) + "\n")

    print(f"target vacancies: {n_t}, company-years ranked: {len(results)}, output: {out}", file=sys.stderr)
    print(f"target skill totals: {totals_out}", file=sys.stderr)
    print(f"target vacancy file: {target_out}", file=sys.stderr)


if __name__ == "__main__":
    main()
