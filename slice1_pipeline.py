"""Command-line entrypoint voor Slice 1.

Voorbeelden:
    python slice1_pipeline.py --target "ABN AMRO"
    python slice1_pipeline.py --target "Jouw Bank" --target-sector "Financial Services" \
        --target-country Netherlands --target-market-cap-usd 5e9
"""

from __future__ import annotations

import argparse
import logging
import sys
import warnings
from datetime import date
from pathlib import Path

from slice1 import PipelineConfig, TargetNotFoundError, run_pipeline
from slice1.config import REGION_SCOPES

HERE = Path(__file__).resolve().parent


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Slice 1: peer-profiling en vacature-export (Contract 1).")
    parser.add_argument("--target", help="Naam van het doelbedrijf (wordt anders interactief gevraagd).")
    parser.add_argument("--input", nargs="+", type=Path,
                        help="Parquet-bestanden met ruwe vacatures (standaard: vacancies_*.parquet naast dit script).")
    parser.add_argument("--output-dir", type=Path, default=HERE / "slice1_output")
    parser.add_argument("--target-symbol", help="Yahoo-symbool van het doelbedrijf (bv. ABN.AS).")
    parser.add_argument("--target-sector", help="Sector-override (bv. 'Financial Services').")
    parser.add_argument("--target-country", help="Land-override (bv. Netherlands).")
    parser.add_argument("--target-market-cap-usd", type=float, help="Marktkapitalisatie-override in USD.")
    parser.add_argument("--region-scope", choices=REGION_SCOPES, default="country",
                        help="Regio-filter voor peers (standaard: zelfde land).")
    parser.add_argument("--min-return", type=float, default=0.0,
                        help="Minimaal koersrendement (0.0 = positief) over de groeivensters.")
    parser.add_argument("--min-company-vacancies", type=int, default=50,
                        help="Bedrijven met minder vacatures worden niet opgezocht op de beurs.")
    parser.add_argument("--as-of", type=date.fromisoformat,
                        help="Peildatum voor koersanalyse (YYYY-MM-DD). Standaard: laatste publicatiedatum.")
    parser.add_argument("--max-companies", type=int, help="Beperk het aantal op te zoeken bedrijven (testen).")
    parser.add_argument("--jsonl", action="store_true", help="Schrijf het contract ook als JSON Lines.")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")
    # yfinance en pandas geven veel deprecatie-ruis; die is niet relevant voor de gebruiker.
    warnings.filterwarnings("ignore", module=r"yfinance.*")
    logging.getLogger("yfinance").setLevel(logging.ERROR)

    target = args.target or (input("Naam van het doelbedrijf: ").strip() if sys.stdin.isatty() else "")
    if not target:
        print("Geen doelbedrijf opgegeven (gebruik --target).", file=sys.stderr)
        return 2

    inputs = tuple(args.input) if args.input else tuple(sorted(HERE.glob("vacancies_*.parquet")))
    if not inputs:
        print("Geen vacature-parquetbestanden gevonden (gebruik --input).", file=sys.stderr)
        return 2

    config = PipelineConfig(
        target_name=target,
        input_files=inputs,
        output_dir=args.output_dir,
        target_symbol=args.target_symbol,
        target_sector=args.target_sector,
        target_country=args.target_country,
        target_market_cap_usd=args.target_market_cap_usd,
        region_scope=args.region_scope,
        min_return=args.min_return,
        min_company_vacancies=args.min_company_vacancies,
        as_of=args.as_of,
        max_companies=args.max_companies,
        write_jsonl=args.jsonl,
    )

    try:
        result = run_pipeline(config)
    except TargetNotFoundError as exc:
        print(f"Fout: {exc}", file=sys.stderr)
        return 1

    print(f"\nDoelbedrijf: {result.target.name} ({result.target.sector}, {result.target.country})")
    print(f"Succesvolle grotere peers ({len(result.successful_peers)}):")
    for peer in result.successful_peers:
        print(f"  - {peer.name} [{peer.symbol}]")
    print(f"Contract 1 geschreven: {config.contract_path} ({result.contract_rows} vacatures)")
    print(f"Rapport: {config.report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
