"""Configuratie en constanten voor de Slice 1 pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

REGION_SCOPES = ("country", "europe", "any")

# Landnamen zoals Yahoo Finance ze teruggeeft (veld `country`).
EUROPEAN_COUNTRIES = frozenset(
    {
        "Austria", "Belgium", "Bulgaria", "Croatia", "Cyprus", "Czech Republic",
        "Czechia", "Denmark", "Estonia", "Finland", "France", "Germany", "Greece",
        "Hungary", "Iceland", "Ireland", "Italy", "Latvia", "Liechtenstein",
        "Lithuania", "Luxembourg", "Malta", "Netherlands", "Norway", "Poland",
        "Portugal", "Romania", "Slovakia", "Slovenia", "Spain", "Sweden",
        "Switzerland", "United Kingdom",
    }
)


@dataclass(frozen=True)
class PipelineConfig:
    """Alle instellingen van één pipeline-run.

    Parameters
    ----------
    target_name:
        Naam van het doelbedrijf, bv. "ABN AMRO".
    input_files:
        Parquet-bestanden met de ruwe vacatures.
    output_dir:
        Map waarin het contract, de bedrijfsprofielen en de cache worden opgeslagen.
    target_symbol, target_sector, target_country, target_market_cap_usd:
        Optionele overrides. Nodig wanneer het doelbedrijf niet op de beurs staat
        (bv. een fictieve bank): dan moeten sector, land en marktkapitalisatie
        handmatig worden opgegeven.
    region_scope:
        "country" (zelfde land), "europe" (Europese landen) of "any" (geen regio-filter).
    min_return:
        Minimale totale koersrendement (adjusted) over de groeivensters. Een peer
        moet over 3 jaar én (indien beschikbaar) over 5 jaar boven deze drempel zitten.
    min_company_vacancies:
        Bedrijven met minder vacatures worden niet opgezocht op de beurs (performance).
    as_of:
        Peildatum voor de koersanalyse. Standaard de laatste `date_posted` in de data.
    max_companies:
        Beperkt het aantal te resolven bedrijven (voor development / snelle tests).
    write_jsonl:
        Schrijf het contract ook als JSON Lines naast het Parquet-bestand.
    """

    target_name: str
    input_files: tuple[Path, ...]
    output_dir: Path = Path("slice1_output")
    target_symbol: str | None = None
    target_sector: str | None = None
    target_country: str | None = None
    target_market_cap_usd: float | None = None
    region_scope: str = "country"
    min_return: float = 0.0
    min_company_vacancies: int = 50
    as_of: date | None = None
    max_companies: int | None = None
    write_jsonl: bool = False

    def __post_init__(self) -> None:
        if self.region_scope not in REGION_SCOPES:
            raise ValueError(f"region_scope moet één van {REGION_SCOPES} zijn")
        if not self.target_name.strip():
            raise ValueError("target_name mag niet leeg zijn")
        if not self.input_files:
            raise ValueError("Geef minstens één parquet-bestand op")

    @property
    def cache_dir(self) -> Path:
        return self.output_dir / "cache"

    @property
    def contract_path(self) -> Path:
        return self.output_dir / "spine_raw_jobs.parquet"

    @property
    def contract_jsonl_path(self) -> Path:
        return self.output_dir / "spine_raw_jobs.jsonl"

    @property
    def company_profiles_path(self) -> Path:
        return self.output_dir / "company_profiles.parquet"

    @property
    def report_path(self) -> Path:
        return self.output_dir / "run_report.json"
