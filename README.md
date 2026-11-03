# Informatigals

## Slice 1: Data Spine & Company Profiling (Python)

Pipeline die de vacatures uit `vacancies_*.parquet` koppelt aan beursdata (yfinance) en Contract 1 (`spine_raw_jobs`) wegschrijft.

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements-slice1.txt
./.venv/bin/python slice1_pipeline.py --target "ABN AMRO"        # of zonder --target om het te vragen
./.venv/bin/python tests/test_slice1.py                            # offline tests
```

Output in `slice1_output/`: `spine_raw_jobs.parquet` (Contract 1, optioneel `--jsonl`), `company_profiles.parquet` (per bedrijf: marktkapitalisatie, koersrendement, peer-status) en `run_report.json`.

Belangrijkste opties: `--region-scope country|europe|any`, `--min-return`, `--min-company-vacancies`, `--as-of`. Voor een doelbedrijf dat niet op de beurs staat: `--target-sector`, `--target-country` en `--target-market-cap-usd` opgeven.

Bekende beperkingen: marktkapitalisatie en medewerkersaantallen zijn een momentopname van Yahoo Finance (niet historisch). Groepsniveau geldt voor dochters (bv. "Santander UK" krijgt de cijfers van Banco Santander). Yahoo-antwoorden worden gecachet in `slice1_output/cache/`; verwijder die map om opnieuw op te zoeken.
