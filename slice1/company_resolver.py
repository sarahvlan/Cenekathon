"""Koppelt een ruwe bedrijfsnaam uit de vacaturedata aan een beursprofiel.

Volgorde van opzoeken:
1. Handmatige aliastabel (`aliases.ALIASES`), inclusief bekende niet-beursgenoteerden.
2. Yahoo-zoekopdracht op de ruwe naam, gevalideerd op naamgelijkenis.
3. Geen match: het bedrijf geldt als niet-beursgenoteerd en komt niet in aanmerking als peer.
"""

from __future__ import annotations

from .aliases import ALIASES
from .market_data import MarketDataClient
from .models import CompanyProfile
from .names import normalize_name


class CompanyResolver:
    def __init__(self, market: MarketDataClient, aliases: dict[str, str | None] | None = None) -> None:
        self._market = market
        self._aliases: dict[str, str | None] = {}
        for raw, symbol in (aliases if aliases is not None else ALIASES).items():
            self._aliases[normalize_name(raw)] = symbol

    def resolve(self, raw_name: str) -> CompanyProfile | None:
        key = normalize_name(raw_name)
        if not key:
            return None

        if key in self._aliases:
            symbol = self._aliases[key]
            if symbol is None:  # bekend als niet-beursgenoteerd
                return None
            return self._market.profile(symbol)

        symbol = self._market.search_symbol(raw_name)
        if symbol is None:
            return None
        return self._market.profile(symbol)
