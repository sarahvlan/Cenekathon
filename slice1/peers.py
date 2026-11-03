"""Peerselectie (sector, regio, grootte) en groeifilter op basis van koersrendement."""

from __future__ import annotations

from collections.abc import Iterable

from .config import EUROPEAN_COUNTRIES
from .models import CompanyProfile


def _same_region(scope: str, candidate: str | None, target: str | None) -> bool:
    if scope == "any":
        return True
    if not candidate or not target:
        return False
    if scope == "country":
        return candidate.casefold() == target.casefold()
    if scope == "europe":
        return candidate in EUROPEAN_COUNTRIES and target in EUROPEAN_COUNTRIES
    raise ValueError(f"Onbekende region_scope: {scope}")


def candidate_peers(
    target: CompanyProfile,
    profiles: Iterable[CompanyProfile],
    region_scope: str = "country",
) -> list[CompanyProfile]:
    """Beursgenoteerde bedrijven met dezelfde sector en regio én een HOGERE marktkapitalisatie.

    Bedrijven zonder sector, land of marktkapitalisatie vallen af. Het doelbedrijf zelf
    wordt uitgesloten.
    """
    if target.market_cap_usd is None:
        raise ValueError("Het doelbedrijf heeft geen marktkapitalisatie; peerselectie is niet mogelijk")

    peers = []
    for profile in profiles:
        if profile.key == target.key or profile.symbol is None:
            continue
        if profile.market_cap_usd is None or profile.sector is None:
            continue
        if profile.sector != target.sector:
            continue
        if not _same_region(region_scope, profile.country, target.country):
            continue
        if profile.market_cap_usd <= target.market_cap_usd:
            continue
        peers.append(profile)
    return peers


def has_positive_growth(returns: dict[str, float | None] | None, min_return: float = 0.0) -> bool:
    """Succesvol groeipad: het 3-jaars rendement is boven `min_return`.

    Het 5-jaars rendement moet ook boven de drempel liggen, tenzij het niet beschikbaar
    is (een bedrijf dat recenter is genoteerd heeft geen 5-jaars historie).
    """
    if not returns:
        return False
    ret_3y = returns.get("ret_3y")
    if ret_3y is None or ret_3y <= min_return:
        return False
    ret_5y = returns.get("ret_5y")
    if ret_5y is not None and ret_5y <= min_return:
        return False
    return True
