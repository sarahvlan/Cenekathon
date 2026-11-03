"""
One-step runner: asks for a company name, runs Slice 1 for it, then matches its
current vacancies against older vacancies of other companies.

Usage (from backend/model/):
    .venv/bin/python run_match.py

Outputs (written by match_company.py):
    output/matches_<company>.csv        ranked company-years, most similar first
    output/target_<company>_2026_skill_totals.json   how many of the company's 2026 vacancies mention each skill
    output/target_<company>_2026_vacancies.json      the company's 2026 vacancies with their important skills
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    company = input("Company name (e.g. KBC): ").strip()
    if not company:
        sys.exit("No company name given.")

    cmd = [sys.executable, str(HERE / "match_company.py"), company, "--run-slice1"]
    print("\nRunning:", " ".join(cmd[1:]), "\n")
    sys.exit(subprocess.run(cmd).returncode)


if __name__ == "__main__":
    main()
