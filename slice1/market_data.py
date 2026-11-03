"""Yahoo Finance-toegang via yfinance, met caching en valutaconversie naar USD.

Alle netwerkfouten worden opgevangen en gelogd. Fouten worden niet gecachet, zodat
een volgende run ze opnieuw probeert. "Bestaat niet" wordt wel gecachet (als None).
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta

import pandas as pd
import yfinance as yf

from .cache import JsonCache
from .models import CompanyProfile
from .names import name_similarity, normalize_name

log = logging.getLogger(__name__)

# Minimale naamgelijkenis om een zoekresultaat als hetzelfde bedrijf te accepteren.
SEARCH_MIN_SIMILARITY = 0.85

# yfinance geeft `currency = "GBp"` (pence) maar `marketCap` in ponden (geverifieerd met
# Barclays: 423,4p x 13,29 mld aandelen = GBP 56 mld). Daarom behandelen we GBp als GBP.
_CURRENCY_ALIASES = {"GBp": "GBP", "GBX": "GBP"}


class MarketDataClient:
    def __init__(self, cache: JsonCache, request_pause: float = 0.2) -> None:
        self._cache = cache
        self._pause_seconds = request_pause

    # ------------------------------------------------------------------ zoeken
    def search_symbol(self, name: str) -> str | None:
        """Zoek het beurssymbool dat het best bij `name` past, of None."""
        key = f"search:{normalize_name(name)}"
        if self._cache.has(key):
            return self._cache.get(key)
        if not normalize_name(name):
            return None

        try:
            quotes = yf.Search(name, max_results=10).quotes or []
        except Exception as exc:  # netwerk/rate-limit: niet cachen
            log.warning("Yahoo-zoekopdracht voor %r mislukt: %s", name, exc)
            return None

        best_symbol, best_score = None, 0.0
        for quote in quotes:
            if quote.get("quoteType") != "EQUITY":
                continue
            for field in ("longname", "shortname"):
                candidate = quote.get(field)
                if not candidate:
                    continue
                score = name_similarity(name, candidate)
                if score > best_score:
                    best_symbol, best_score = quote.get("symbol"), score

        symbol = best_symbol if best_score >= SEARCH_MIN_SIMILARITY else None
        self._cache.set(key, symbol)
        self._pause()
        return symbol

    # ---------------------------------------------------------------- profiel
    def profile(self, symbol: str) -> CompanyProfile | None:
        """Haal sector, land, marktkapitalisatie (USD) en medewerkers op voor een symbool."""
        key = f"profile:{symbol}"
        if self._cache.has(key):
            data = self._cache.get(key)
        else:
            try:
                data = self._fetch_profile(symbol)
            except Exception as exc:
                log.warning("Yahoo-profiel voor %s mislukt: %s", symbol, exc)
                return None
            self._cache.set(key, data)
            self._pause()

        if data is None:
            return None
        return CompanyProfile(
            key=symbol,
            name=data["name"],
            symbol=symbol,
            sector=data.get("sector"),
            country=data.get("country"),
            market_cap_usd=data.get("market_cap_usd"),
            employee_count=data.get("employee_count"),
        )

    def _fetch_profile(self, symbol: str) -> dict | None:
        info = yf.Ticker(symbol).info or {}
        if info.get("quoteType") != "EQUITY":
            return None

        market_cap = info.get("marketCap")
        market_cap_usd = self._to_usd(market_cap, info.get("currency")) if market_cap else None
        employees = info.get("fullTimeEmployees")
        return {
            "name": info.get("longName") or info.get("shortName") or symbol,
            "sector": info.get("sector"),
            "country": info.get("country"),
            "market_cap_usd": market_cap_usd,
            "employee_count": int(employees) if employees else None,
        }

    # --------------------------------------------------------------- koersen
    def price_returns(self, symbol: str, as_of: date, windows_years: tuple[int, ...]) -> dict[str, float | None] | None:
        """Totaal koersrendement (adjusted) per venster, eindigend op `as_of`.

        Geeft bv. {"ret_3y": 0.42, "ret_5y": None}. None als er geen koersdata is.
        """
        windows = ",".join(str(w) for w in windows_years)
        key = f"returns:{symbol}:{as_of.isoformat()}:{windows}"
        if self._cache.has(key):
            return self._cache.get(key)

        try:
            start = (pd.Timestamp(as_of) - pd.DateOffset(years=max(windows_years) + 1)).date()
            history = yf.Ticker(symbol).history(
                start=start.isoformat(),
                end=(as_of + timedelta(days=1)).isoformat(),
                interval="1mo",
                auto_adjust=True,
            )
        except Exception as exc:
            log.warning("Koersdata voor %s mislukt: %s", symbol, exc)
            return None

        result: dict[str, float | None] = {f"ret_{w}y": None for w in windows_years}
        close = history["Close"].dropna() if not history.empty else pd.Series(dtype=float)
        if not close.empty:
            if close.index.tz is not None:
                close.index = close.index.tz_localize(None)
            end_price = close.asof(pd.Timestamp(as_of))
            for years in windows_years:
                start_price = close.asof(pd.Timestamp(as_of) - pd.DateOffset(years=years))
                if pd.notna(end_price) and pd.notna(start_price) and start_price > 0:
                    result[f"ret_{years}y"] = float(end_price / start_price - 1.0)

        self._cache.set(key, result)
        self._pause()
        return result

    # ---------------------------------------------------------------- valuta
    def _to_usd(self, amount: float | None, currency: str | None) -> float | None:
        if amount is None or not currency:
            return None
        ccy = _CURRENCY_ALIASES.get(currency, currency).upper()
        rate = self._fx_to_usd(ccy)
        return None if rate is None else float(amount) * rate

    def _fx_to_usd(self, currency: str) -> float | None:
        if currency == "USD":
            return 1.0
        key = f"fx:{currency}"
        if self._cache.has(key):
            return self._cache.get(key)
        try:
            history = yf.Ticker(f"{currency}USD=X").history(period="1mo")
            rate = float(history["Close"].dropna().iloc[-1])
        except Exception as exc:
            log.warning("Wisselkoers %s/USD niet beschikbaar: %s", currency, exc)
            return None
        self._cache.set(key, rate)
        return rate

    def _pause(self) -> None:
        if self._pause_seconds > 0:
            time.sleep(self._pause_seconds)
