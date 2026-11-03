"""Datamodellen die tussen de modules worden doorgegeven."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompanyProfile:
    """Beursgegevens van een bedrijf, of de gegevens die daarvoor zijn ingevuld.

    `key` is het Yahoo-symbool (bv. "INGA.AS") als het bedrijf beursgenoteerd is,
    anders `"name:<genormaliseerde naam>"`. Met de key worden vacatureregels aan
    een bedrijf gekoppeld, ongeacht de schrijfwijze van de naam in de data.
    """

    key: str
    name: str
    symbol: str | None
    sector: str | None
    country: str | None
    market_cap_usd: float | None
    employee_count: int | None
